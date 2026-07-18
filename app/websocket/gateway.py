"""WebSocket Gateway for VEYAAN device connections."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.cache import valkey_client
from app.config import settings
from app.database.connection import close_db, init_db
from app.database.session import get_db_session_context as get_db_session
from app.devices.models import DeviceStatus
from app.devices.repository import DeviceRepository
from app.emergency_stop.service import EmergencyStopService
from app.events import subjects
from app.events.nats_client import nats_client
from app.websocket.protocol.challenge import generate_challenge, verify_device_challenge_response
from app.websocket.protocol.messages import (
    CommandRequestMessage,
    EmergencyStopMessage,
    ResumeAfterEmergencyStopMessage,
    WelcomeMessage,
)
from app.websocket.protocol.validator import ProtocolError, ProtocolValidator

logger = structlog.get_logger(__name__)


class DeviceConnection:
    def __init__(self, device_id: UUID, owner_id: UUID, connection_id: UUID, websocket: WebSocket):
        self.device_id = device_id
        self.owner_id = owner_id  # stored for emergency-stop lookups
        self.connection_id = connection_id
        self.websocket = websocket
        self.authenticated_at = datetime.now(timezone.utc)
        self.last_heartbeat = datetime.now(timezone.utc)
        self.protocol_version = "v1"
        self.app_version = ""
        self.gateway_instance_id = str(uuid4())
        self.violations = 0

    async def send_json(self, data: dict) -> bool:
        try:
            await self.websocket.send_json(data)
            return True
        except Exception as e:
            logger.error("send_failed", device_id=str(self.device_id), error=str(e))
            return False

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception:
            pass


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[UUID, DeviceConnection] = {}

    async def register(self, connection: DeviceConnection) -> None:
        device_id = connection.device_id
        old = self.active_connections.get(device_id)
        if old:
            await old.close(code=4000, reason="Replaced by new connection")
        self.active_connections[device_id] = connection
        await valkey_client.set_hash(
            f"device:connection:{device_id}",
            {
                "connection_id": str(connection.connection_id),
                "gateway_id": connection.gateway_instance_id,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            },
            ttl=180,
        )

    async def unregister(self, device_id: UUID, connection_id: UUID) -> None:
        # Check Valkey to ensure we don't delete a newer connection's presence on disconnect (old-disconnect race)
        valkey_conn = await valkey_client.get_hash(f"device:connection:{device_id}")
        if valkey_conn and valkey_conn.get("connection_id") == str(connection_id):
            await valkey_client.delete_hash(f"device:connection:{device_id}")
            await valkey_client.delete(f"device:presence:{device_id}")

        conn = self.active_connections.get(device_id)
        if conn and conn.connection_id == connection_id:
            del self.active_connections[device_id]

    def get(self, device_id: UUID) -> Optional[DeviceConnection]:
        return self.active_connections.get(device_id)

    def is_connected(self, device_id: UUID) -> bool:
        return device_id in self.active_connections

    async def send_command(
        self, device_id: UUID, owner_id: UUID, message: CommandRequestMessage
    ) -> bool:
        """Send command to device — blocks if emergency stop is active for this owner."""
        # GAP-P0-4: Check emergency stop before every send (database is authoritative via service)
        from app.emergency_stop.service import EmergencyStopService

        estop_service = EmergencyStopService()
        if await estop_service.is_active(owner_id):
            logger.warning(
                "command_blocked_by_emergency_stop",
                device_id=str(device_id),
                owner_id=str(owner_id),
                command_id=str(message.command_id),
            )
            return False

        conn = self.get(device_id)
        if not conn:
            return False
        return await conn.send_json(message.model_dump(mode="json"))

    async def close_device_connection(
        self, device_id: UUID, reason: str = "Connection closed by server"
    ) -> None:
        """Force-close a device's connection — used by device revocation."""
        conn = self.get(device_id)
        if conn:
            await conn.close(code=4002, reason=reason)
            await self.unregister(device_id, conn.connection_id)
            logger.info("device_connection_force_closed", device_id=str(device_id), reason=reason)

    async def broadcast_emergency_stop(
        self, owner_id: UUID, active: bool, reason: str = ""
    ) -> None:
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            devices = await repo.list_devices_by_owner(owner_id)
            for device in devices:
                conn = self.get(device.id)
                if conn:
                    if active:
                        msg = EmergencyStopMessage(reason=reason)
                    else:
                        msg = ResumeAfterEmergencyStopMessage()
                    await conn.send_json(msg.model_dump(mode="json"))


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
    await nats_client.connect()

    # Subscribe WebSocket gateway globally to NATS security event broadcasts
    if nats_client.nc:
        await nats_client.nc.subscribe("veyaan.security.>", cb=security_callback)
        logger.info("Subscribed WebSocket Gateway to veyaan.security.>")

    logger.info("Gateway startup complete")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down WebSocket Gateway")
    await nats_client.disconnect()
    await valkey_client.disconnect()
    await close_db()


async def _get_device_for_auth(device_id: UUID) -> Optional[object]:
    """Load device + verify it is trusted and not revoked."""
    async with get_db_session() as session:
        repo = DeviceRepository(session)
        device = await repo.get_device(device_id)
        if not device:
            return None
        if device.trust_status != DeviceStatus.TRUSTED or device.revoked_at:
            return None
        return device


@app.websocket("/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    protocol_version: str = "v1",
    app_version: str = "",
):
    """
    Challenge-response WebSocket authentication flow (GAP-P0-1):
      1. Accept connection
      2. Validate protocol version
      3. Send auth_challenge with a one-time nonce
      4. Wait for auth_response with device_id + Ed25519 signature
      5. Verify signature against stored public key
      6. Fetch real emergency-stop state (GAP-P0-2)
      7. Send welcome and proceed

    No device secret is ever placed in the URL or query string.
    """
    connection_id = uuid4()
    server_time = datetime.now(timezone.utc)
    server_time_iso = server_time.isoformat()

    try:
        ProtocolValidator.validate_protocol_version(protocol_version)
    except ProtocolError as e:
        await websocket.close(code=4003, reason=e.message)
        return

    await websocket.accept()

    # Step 1: Send challenge nonce along with connection_id and server_time
    nonce = await generate_challenge()
    await websocket.send_json(
        {
            "type": "auth_challenge",
            "nonce": nonce,
            "connection_id": str(connection_id),
            "server_time": server_time_iso,
            "supported_protocols": ["v1"],
        }
    )

    # Step 2: Wait for auth_response (with timeout)
    try:
        raw = await asyncio.wait_for(websocket.receive_bytes(), timeout=15.0)
    except asyncio.TimeoutError:
        await websocket.send_json(
            {"type": "error", "code": "AUTH_TIMEOUT", "message": "Authentication timed out"}
        )
        await websocket.close(code=4001, reason="Auth timeout")
        return
    except Exception:
        await websocket.close(code=4001, reason="Connection error during auth")
        return

    # Step 3: Parse auth_response
    try:
        auth_data = json.loads(raw.decode("utf-8"))
    except Exception:
        await websocket.send_json(
            {"type": "error", "code": "INVALID_JSON", "message": "Invalid auth response"}
        )
        await websocket.close(code=4001, reason="Invalid JSON")
        return

    if auth_data.get("type") != "auth_response":
        await websocket.send_json(
            {"type": "error", "code": "AUTH_FAILED", "message": "Expected auth_response"}
        )
        await websocket.close(code=4001, reason="Protocol error")
        return

    device_id_str = auth_data.get("device_id", "")
    signature_b64 = auth_data.get("signature", "")
    client_protocol = auth_data.get("protocol_version", protocol_version)
    client_app_version = auth_data.get("app_version", app_version)
    auth_server_time = auth_data.get("server_time", server_time_iso)

    try:
        device_id = UUID(device_id_str)
    except (ValueError, AttributeError):
        await websocket.send_json(
            {"type": "error", "code": "AUTH_FAILED", "message": "Invalid device_id"}
        )
        await websocket.close(code=4001, reason="Invalid device_id")
        return

    # Step 4: Load device and verify it is trusted
    async with get_db_session() as session:
        repo = DeviceRepository(session)
        device = await repo.get_device(device_id)
        if not device or device.trust_status != DeviceStatus.TRUSTED or device.revoked_at:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "AUTH_FAILED",
                    "message": "Device not found or not trusted",
                }
            )
            await websocket.close(code=4001, reason="Device not authorized")
            return
        public_key_b64 = device.device_public_identity
        owner_id = device.owner_id

    # Step 5: Challenge-response verification (with connection parameters)
    ok, err = await verify_device_challenge_response(
        device_id=device_id,
        connection_id=connection_id,
        nonce=nonce,
        server_time_iso=auth_server_time,
        signature_b64=signature_b64,
        public_key_b64=public_key_b64,
        protocol_version=client_protocol,
        app_version=client_app_version,
    )
    if not ok:
        logger.warning("device_auth_failed", device_id=str(device_id), reason=err)
        await websocket.send_json(
            {"type": "error", "code": "AUTH_FAILED", "message": "Authentication failed"}
        )
        await websocket.close(code=4001, reason="Auth failed")
        return

    # Step 6: Fetch real emergency-stop state (GAP-P0-2)
    estop_service = EmergencyStopService()
    emergency_stop_active = await estop_service.is_active(owner_id)

    conn = DeviceConnection(device_id, owner_id, connection_id, websocket)
    conn.protocol_version = client_protocol
    conn.app_version = client_app_version

    # Step 7: Send Welcome with real emergency-stop state
    welcome = WelcomeMessage(
        connection_id=connection_id,
        server_time=datetime.now(timezone.utc),
        heartbeat_interval=settings.WS_HEARTBEAT_INTERVAL,
        protocol_version="v1",
        emergency_stop_active=emergency_stop_active,
    )
    await websocket.send_json(welcome.model_dump(mode="json"))
    await connection_manager.register(conn)

    logger.info("device_connected", device_id=str(device_id), connection_id=str(connection_id))

    sub = None
    try:
        sub = await nats_client.js.pull_subscribe(
            subjects.command_ready(str(device_id)),
            durable=f"gw_{device_id}",
            stream=settings.NATS_STREAM_COMMANDS,
        )

        async def nats_listener():
            while True:
                try:
                    msgs = await sub.fetch(batch=1, timeout=1)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode())
                            cmd_id = payload["command_id"]

                            # GAP-P0-4: Emergency-stop check before delivery
                            is_stopped = await estop_service.is_active(owner_id)
                            if is_stopped:
                                logger.warning(
                                    "command_blocked_emergency_stop_gateway", command_id=cmd_id
                                )
                                # NAK to retry later when stop is released
                                await msg.nak()
                                continue

                            cmd_msg = CommandRequestMessage(
                                command_id=UUID(cmd_id),
                                command_type=payload["command_type"],
                                parameters=payload.get("parameters", {}),
                                expires_at=payload.get("expires_at"),
                                risk_metadata={"level": payload.get("risk_level", "low")},
                                trace_id=payload.get("trace_id", str(uuid4())),
                            )
                            sent = await conn.send_json(cmd_msg.model_dump(mode="json"))
                            if sent:
                                await nats_client.publish_js(
                                    subjects.command_delivered(cmd_id),
                                    {"command_id": cmd_id, "device_id": str(device_id)},
                                    message_id=f"delivered-{cmd_id}",
                                )
                            # GAP-P0-3: ACK after send (result persistence handled by command_consumer worker)
                            await msg.ack()
                        except Exception as e:
                            logger.exception("nats_msg_error", error=str(e))
                            await msg.nak()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if "connection closed" in str(e).lower():
                        break
                    logger.exception("nats_listener_error", error=str(e))
                    await asyncio.sleep(1)

        nats_task = asyncio.create_task(nats_listener())

        try:
            while True:
                data = await websocket.receive_bytes()
                ProtocolValidator.validate_message_size(data)
                await handle_device_message(device_id, owner_id, data)
        except WebSocketDisconnect:
            logger.info("device_disconnected", device_id=str(device_id))
        except ProtocolError as e:
            logger.warning(
                "protocol_error_ws_endpoint",
                device_id=str(device_id),
                code=e.code,
                message=e.message,
            )
            if e.code == "MESSAGE_TOO_LARGE":
                await websocket.close(code=1009, reason=e.message)
            else:
                await websocket.close(code=4000, reason=e.message)
        except Exception as e:
            logger.exception("websocket_error", device_id=str(device_id), error=str(e))
        finally:
            nats_task.cancel()
    except Exception as e:
        logger.error("nats_subscription_error", device_id=str(device_id), error=str(e))
    finally:
        await connection_manager.unregister(device_id, connection_id)


async def handle_device_message(device_id: UUID, owner_id: UUID, data: bytes) -> None:
    """
    Handle messages from a connected Mac device.
    All ack/result messages validate that command_id belongs to this device (GAP-P1-2).
    """
    try:
        msg = ProtocolValidator.parse_client_message(data)
        logger.debug("message_received", device_id=str(device_id), type=msg.type)

        if msg.type == "heartbeat":
            conn = connection_manager.get(device_id)
            if conn:
                conn.last_heartbeat = datetime.now(timezone.utc)
            await valkey_client.set_hash(
                f"device:presence:{device_id}",
                {
                    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                    "state": getattr(msg, "state", "online"),
                    "active_command_count": getattr(msg, "active_command_count", 0),
                },
                ttl=90,
            )

        elif msg.type == "acknowledge":
            # GAP-P1-2: Verify command belongs to this device before processing
            if not await _command_belongs_to_device(msg.command_id, device_id):
                logger.warning(
                    "ack_command_ownership_mismatch",
                    command_id=str(msg.command_id),
                    device_id=str(device_id),
                )
                return
            await nats_client.publish(
                subjects.command_acknowledged(str(msg.command_id)),
                json.dumps(
                    {
                        "command_id": str(msg.command_id),
                        "device_id": str(device_id),
                        "accepted": msg.accepted,
                        "rejection_reason": getattr(msg, "rejection_reason", None),
                    }
                ).encode(),
            )

        elif msg.type == "progress":
            if not await _command_belongs_to_device(msg.command_id, device_id):
                logger.warning(
                    "progress_command_ownership_mismatch",
                    command_id=str(msg.command_id),
                    device_id=str(device_id),
                )
                return
            await nats_client.publish(
                subjects.command_progress(str(msg.command_id)),
                json.dumps(
                    {
                        "command_id": str(msg.command_id),
                        "device_id": str(device_id),
                        "progress_percent": getattr(msg, "progress_percent", None),
                        "stage": getattr(msg, "stage", None),
                    }
                ).encode(),
            )

        elif msg.type == "result":
            # GAP-P1-2: Verify command belongs to this device
            if not await _command_belongs_to_device(msg.command_id, device_id):
                logger.warning(
                    "result_command_ownership_mismatch",
                    command_id=str(msg.command_id),
                    device_id=str(device_id),
                )
                return
            await nats_client.publish(
                subjects.command_result(str(msg.command_id)),
                json.dumps(
                    {
                        "command_id": str(msg.command_id),
                        "device_id": str(device_id),
                        "success": msg.success,
                        "result_data": getattr(msg, "result_data", None),
                        "error_code": getattr(msg, "error_code", None),
                        "error_message": getattr(msg, "error_message", None),
                        "started_at": msg.started_at.isoformat()
                        if hasattr(msg, "started_at") and msg.started_at
                        else None,
                        "finished_at": msg.finished_at.isoformat()
                        if hasattr(msg, "finished_at") and msg.finished_at
                        else None,
                    }
                ).encode(),
            )

        elif msg.type == "status_update":
            await nats_client.publish(
                subjects.device_lifecycle(str(device_id)),
                json.dumps({"device_id": str(device_id), "state": msg.state}).encode(),
            )

        else:
            logger.warning("unhandled_message_type", type=msg.type, device_id=str(device_id))

    except ProtocolError as e:
        logger.warning("protocol_error", device_id=str(device_id), code=e.code, message=e.message)
        conn = connection_manager.get(device_id)
        if conn:
            conn.violations += 1
            if conn.violations >= 5:
                logger.error("max_protocol_violations_exceeded", device_id=str(device_id))
                await conn.close(code=4005, reason="Too many protocol violations")
    except Exception as e:
        logger.exception("message_handling_error", device_id=str(device_id), error=str(e))


async def _command_belongs_to_device(command_id: UUID, device_id: UUID) -> bool:
    """Verify that a command_id was assigned to this specific device (ownership check)."""
    try:
        from sqlalchemy import select

        from app.commands.models import Command

        async with get_db_session() as session:
            result = await session.execute(
                select(Command.device_id).where(Command.id == command_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            return str(row) == str(device_id)
    except Exception as e:
        logger.error("command_ownership_check_failed", command_id=str(command_id), error=str(e))
        return False


async def security_callback(msg):
    try:
        subject = msg.subject
        data = json.loads(msg.data.decode())
        logger.info("received_security_event", subject=subject, data=data)

        parts = subject.split(".")
        # veyaan.security.emergency_stop.owner_id
        # veyaan.security.emergency_resume.owner_id
        if len(parts) >= 4:
            action = parts[2]
            owner_id = UUID(parts[3])
            active = action == "emergency_stop"
            reason = data.get("reason", "")
            await connection_manager.broadcast_emergency_stop(owner_id, active, reason)
    except Exception as e:
        logger.exception("security_event_processing_failed", error=str(e))


def _validate_protocol_version(version: str | None) -> bool:
    """
    Check if the requested protocol version is in the server's supported list.
    Returns True if valid, False if unsupported or empty.
    """
    if not version:
        return False
    return version in settings.WS_SUPPORTED_PROTOCOLS


@app.get("/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    checks = {}
    try:
        await valkey_client.client.ping()
        checks["valkey"] = "ready"
    except Exception as e:
        checks["valkey"] = f"not_ready: {e}"
    if nats_client.is_connected:
        checks["nats"] = "ready"
    else:
        checks["nats"] = "not_ready"
    all_ready = all(v == "ready" for v in checks.values())
    # GAP-P0-7: Return 503 when not ready
    return JSONResponse(
        content={"ready": all_ready, "checks": checks}, status_code=200 if all_ready else 503
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
