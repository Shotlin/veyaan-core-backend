import hmac
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import nats
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.cache import valkey_client
from app.config import settings
from app.database.connection import close_db, get_session, init_db
from app.devices.models import DeviceStatus
from app.devices.repository import DeviceRepository
from app.events.nats_client import nats_client
from app.websocket.protocol.messages import (
    WelcomeMessage,
)
from app.websocket.protocol.validator import ProtocolError, ProtocolValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[UUID, DeviceConnection] = {}
        self.device_to_connection: dict[UUID, UUID] = {}  # device_id -> connection_id

    async def register_connection(self, device_id: UUID, connection_id: UUID) -> None:
        """Register a new device connection."""
        # Close existing connection if any
        if device_id in self.active_connections:
            old_conn = self.active_connections[device_id]
            await old_conn.close(code=4000, reason="Replaced by new connection")

        self.active_connections[device_id] = DeviceConnection(connection_id)
        self.device_to_connection[device_id] = connection_id

        # Store in Valkey for distributed presence
        await valkey_client.set_hash(
            f"device:connection:{device_id}",
            {
                "connection_id": str(connection_id),
                "connected_at": datetime.now(timezone.utc).isoformat(),
            },
            ttl=180,
        )

    async def unregister_connection(self, device_id: UUID) -> None:
        """Unregister a device connection."""
        if device_id in self.active_connections:
            del self.active_connections[device_id]
        if device_id in self.device_to_connection:
            del self.device_to_connection[device_id]
        await valkey_client.delete_hash(f"device:connection:{device_id}")

    def get_connection(self, device_id: UUID) -> "DeviceConnection | None":
        return self.active_connections.get(device_id)

    def is_connected(self, device_id: UUID) -> bool:
        return device_id in self.active_connections

    async def send_message(self, device_id: UUID, message) -> bool:
        """Send a message to a device."""
        conn = self.active_connections.get(device_id)
        if not conn:
            return False

        try:
            data = ProtocolValidator.serialize_server_message(message)
            await conn.websocket.send_bytes(data)
            return True
        except Exception as e:
            logger.error("send_failed", device_id=str(device_id), error=str(e))
            return False

    async def send_error(self, device_id: UUID, code: str, message: str) -> None:
        """Send error to device and close connection."""
        conn = self.active_connections.get(device_id)
        if conn:
            try:
                error_msg = json.dumps({"type": "error", "code": code, "message": message})
                await conn.websocket.send_text(error_msg)
            except Exception:
                pass


class DeviceConnection:
    def __init__(self, connection_id: UUID):
        self.connection_id = connection_id
        self.websocket: WebSocket | None = None

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.websocket:
            try:
                await self.websocket.close(code=code, reason=reason)
            except Exception:
                pass


# Global instances
connection_manager = ConnectionManager()


app = FastAPI(title="VEYAAN WebSocket Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logger.info("Starting WebSocket Gateway")
    await init_db()
    await valkey_client.connect()

    # Connect to NATS
    nats_client.nc = await nats.connect(settings.NATS_URL)
    nats_client.js = nats_client.nc.jetstream()
    logger.info("NATS connected")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down WebSocket Gateway")
    await nats_client.nc.close()
    await valkey_client.disconnect()
    await close_db()


@app.websocket("/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    device_id: UUID = Query(...),
    credential_proof: str = Query(...),
    protocol_version: str = Query(...),
    app_version: str = Query(...),
):
    """WebSocket endpoint for device connections."""

    # Validate protocol version
    ProtocolValidator.validate_protocol_version(protocol_version)

    # Validate message size
    await websocket.accept()

    # Create device connection
    connection_id = uuid4()
    device_conn = DeviceConnection(connection_id)
    device_conn.websocket = websocket

    # Verify device credentials
    async with get_session() as session:
        repo = DeviceRepository(session)
        device = await repo.get_device(device_id)

        if not device:
            await websocket.close(code=4001, reason="Device not found")
            return

        if device.trust_status != DeviceStatus.TRUSTED or device.revoked_at:
            await websocket.close(code=4002, reason="Device not trusted or revoked")
            return

        # Verify credential
        credential = await repo.get_active_credential(device_id)
        if not credential:
            await websocket.close(code=4003, reason="No valid credential")
            return

        # Simple proof verification
        if not hmac.compare_digest(credential_proof, credential.credential_hash):
            await websocket.close(code=4004, reason="Invalid credential proof")
            return

    # Register connection
    await connection_manager.register_connection(device_id, connection_id)

    # Send welcome message
    welcome = WelcomeMessage(
        connection_id=connection_id,
        server_time=datetime.now(timezone.utc),
        heartbeat_interval=settings.WS_HEARTBEAT_INTERVAL,
        protocol_version="v1",
        emergency_stop_active=False,  # Check from cache
    )
    await websocket.send_bytes(ProtocolValidator.serialize_server_message(welcome))

    logger.info("device_connected", device_id=str(device_id), connection_id=str(connection_id))

    try:
        while True:
            # Receive message with size limit
            data = await websocket.receive_bytes()
            ProtocolValidator.validate_message_size(data)

            # Handle message
            await handle_device_message(device_id, data)

    except WebSocketDisconnect:
        logger.info("device_disconnected", device_id=str(device_id))
    except Exception as e:
        logger.exception("websocket_error", device_id=str(device_id), error=str(e))
    finally:
        await connection_manager.unregister_connection(device_id)


async def handle_device_message(device_id: UUID, data: bytes) -> None:
    """Handle incoming device message."""
    try:
        # Parse message using protocol validator
        from app.websocket.protocol.validator import ProtocolValidator
        msg = ProtocolValidator.parse_client_message(data)

        logger.debug("message_received", device_id=str(device_id), type=msg.type)

        if msg.type == "heartbeat":
            await handle_heartbeat(device_id, msg)
        elif msg.type == "acknowledge":
            await handle_acknowledge(device_id, msg)
        elif msg.type == "progress":
            await handle_progress(device_id, msg)
        elif msg.type == "result":
            await handle_result(device_id, msg)
        elif msg.type == "status_update":
            await handle_status_update(device_id, msg)
        else:
            logger.warning("unhandled_message_type", type=msg.type, device_id=str(device_id))

    except ProtocolError as e:
        logger.warning("protocol_error", device_id=str(device_id), code=e.code, message=e.message)
        await connection_manager.send_error(device_id, e.code, e.message)
    except Exception as e:
        logger.exception("message_handling_error", device_id=str(device_id), error=str(e))
        await connection_manager.send_error(device_id, "INTERNAL_ERROR", "Internal server error")


async def handle_heartbeat(device_id: UUID, msg) -> None:
    """Handle heartbeat from device."""
    # Update presence in Valkey
    await valkey_client.set_hash(
        f"device:presence:{device_id}",
        {
            "state": msg.state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "active_commands": msg.active_command_count,
            "app_version": msg.app_version,
        },
        ttl=90,  # 3x heartbeat interval
    )

    logger.debug("heartbeat_received", device_id=str(device_id), state=msg.state)


async def handle_acknowledge(device_id: UUID, msg) -> None:
    """Handle command acknowledgement from device."""
    logger.info("command_acknowledged", device_id=str(device_id), command_id=str(msg.command_id), accepted=msg.accepted)

    # Publish to NATS for backend processing
    await nats_client.publish(
        f"veyaan.commands.ack.{msg.command_id}",
        msg.model_dump_json().encode(),
    )


async def handle_progress(device_id: UUID, msg) -> None:
    """Handle command progress update."""
    logger.debug("command_progress", device_id=str(device_id), command_id=str(msg.command_id), progress=msg.progress_percent)


async def handle_result(device_id: UUID, msg) -> None:
    """Handle command completion result."""
    logger.info("command_completed", device_id=str(device_id), command_id=str(msg.command_id), success=msg.success)

    # Publish to NATS for backend processing
    await nats_client.publish(
        f"veyaan.commands.result.{msg.command_id}",
        msg.model_dump_json().encode(),
    )


async def handle_status_update(device_id: UUID, msg) -> None:
    """Handle device status update."""
    await valkey_client.set_hash(
        f"device:presence:{device_id}",
        {
            "state": msg.state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": json.dumps(msg.metadata) if msg.metadata else "{}",
        },
        ttl=90,
    )


@app.get("/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    checks = {}

    # Valkey
    try:
        await valkey_client.client.ping()
        checks["valkey"] = "ready"
    except Exception as e:
        checks["valkey"] = f"not_ready: {e}"

    # NATS
    if nats_client.nc and nats_client.nc.is_connected:
        checks["nats"] = "ready"
    else:
        checks["nats"] = "not_ready"

    all_ready = all(v == "ready" for v in checks.values())
    return {"ready": all_ready, "checks": checks}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
