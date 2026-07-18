import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.cache import valkey_client
from app.database.session import get_db_session
from app.devices.models import DeviceStatus
from app.devices.repository import DeviceRepository
from app.events.nats_client import nats_client
from app.websocket.protocol.messages import (
    ServerMessage,
)
from app.websocket.protocol.validator import ProtocolValidator

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[UUID, DeviceConnection] = {}
        self.connection_id_map: dict[UUID, UUID] = {}  # device_id -> connection_id

    async def register(self, device_id: UUID, connection: "DeviceConnection") -> UUID:
        # Close existing connection for this device if any
        if device_id in self.active_connections:
            old_conn = self.active_connections[device_id]
            await old_conn.close(code=4000, reason="Replaced by new connection")
            logger.info("Closed existing connection for device", extra={"device_id": str(device_id)})

        connection_id = uuid4()
        self.active_connections[device_id] = connection
        self.connection_id_map[device_id] = connection_id

        # Store in Valkey for distributed presence
        await valkey_client.set_hash(
            f"device:connection:{device_id}",
            {
                "connection_id": str(connection_id),
                "connected_at": datetime.now(timezone.utc).isoformat(),
            },
            ttl=180,  # 3 minutes (covers heartbeat timeout)
        )
        return connection_id

    async def unregister(self, device_id: UUID) -> None:
        if device_id in self.active_connections:
            del self.active_connections[device_id]
        if device_id in self.connection_id_map:
            del self.connection_id_map[device_id]
        await valkey_client.delete_hash(f"device:connection:{device_id}")
        await valkey_client.delete(f"device:presence:{device_id}")

    def get_connection(self, device_id: UUID) -> "DeviceConnection | None":
        return self.active_connections.get(device_id)

    def is_connected(self, device_id: UUID) -> bool:
        return device_id in self.active_connections


class DeviceConnection:
    def __init__(self, websocket, device_id: UUID, connection_id: UUID, manager: ConnectionManager):
        self.websocket = websocket
        self.device_id = device_id
        self.connection_id = connection_id
        self.manager = manager
        self.last_heartbeat = datetime.now(timezone.utc)
        self.active_command_count = 0

    async def send(self, message: ServerMessage) -> bool:
        try:
            data = ProtocolValidator.serialize_server_message(message)
            await self.websocket.send_bytes(data)
            return True
        except Exception as e:
            logger.error("Failed to send message", extra={"device_id": str(self.device_id), "error": str(e)})
            return False

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception:
            pass


class MessageHandler:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager

    async def handle_hello(self, conn: DeviceConnection, msg) -> None:
        """Handle initial hello/authentication message."""
        # This is handled during connection setup, not here
        pass

    async def handle_heartbeat(self, conn: DeviceConnection, msg) -> None:
        """Handle heartbeat from device."""
        conn.last_heartbeat = datetime.now(timezone.utc)
        conn.active_command_count = msg.active_command_count

        # Update presence in Valkey
        await valkey_client.set_hash(
            f"device:presence:{conn.device_id}",
            {
                "state": msg.state,
                "updated_at": conn.last_heartbeat.isoformat(),
                "active_commands": msg.active_command_count,
                "app_version": msg.app_version,
            },
            ttl=90,  # 3x heartbeat interval
        )

        # Also update device last_seen in database periodically
        # (We could do this less frequently to reduce DB load)

        logger.debug("Heartbeat received", extra={
            "device_id": str(conn.device_id),
            "state": msg.state,
            "active_commands": msg.active_command_count,
        })

    async def handle_acknowledge(self, conn: DeviceConnection, msg) -> None:
        """Handle command acknowledgement from device."""
        logger.info("Command acknowledged", extra={
            "device_id": str(conn.device_id),
            "command_id": str(msg.command_id),
            "accepted": msg.accepted,
        })

        if not msg.accepted:
            # Handle rejection
            await self._handle_command_rejection(conn, msg)

    async def handle_progress(self, conn: DeviceConnection, msg) -> None:
        """Handle command progress update."""
        logger.debug("Command progress", extra={
            "device_id": str(conn.device_id),
            "command_id": str(msg.command_id),
            "progress": msg.progress_percent,
            "stage": msg.stage,
        })

    async def handle_result(self, conn: DeviceConnection, msg) -> None:
        """Handle command completion result."""
        logger.info("Command completed", extra={
            "device_id": str(conn.device_id),
            "command_id": str(msg.command_id),
            "success": msg.success,
        })

        # Publish result to NATS for backend processing
        await nats_client.publish(
            f"veyaan.commands.result.{msg.command_id}",
            msg.model_dump_json().encode(),
        )

    async def handle_status_update(self, conn: DeviceConnection, msg) -> None:
        """Handle device status update."""
        await valkey_client.set_hash(
            f"device:presence:{conn.device_id}",
            {
                "state": msg.state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "metadata": msg.metadata or {},
            },
            ttl=90,
        )

    async def _handle_command_rejection(self, conn: DeviceConnection, msg) -> None:
        """Handle rejected command - publish rejection event."""
        logger.warning("Command rejected by device", extra={
            "device_id": str(conn.device_id),
            "command_id": str(msg.command_id),
            "reason": msg.rejection_reason,
        })

    async def dispatch(self, conn: DeviceConnection, message) -> None:
        """Dispatch message to appropriate handler."""
        msg_type = message.type

        handlers = {
            "heartbeat": self.handle_heartbeat,
            "acknowledge": self.handle_acknowledge,
            "progress": self.handle_progress,
            "result": self.handle_result,
            "status_update": self.handle_status_update,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(conn, message)
        else:
            logger.warning("Unhandled message type", extra={"type": msg_type, "device_id": str(conn.device_id)})


async def authenticate_device(device_id: UUID, credential_proof: str, protocol_version: str, app_version: str) -> tuple[bool, str | None]:
    """Authenticate device using credential proof (HMAC)."""
    ProtocolValidator.validate_protocol_version(protocol_version)

    async with get_db_session() as session:
        repo = DeviceRepository(session)
        device = await repo.get_device(device_id)

        if not device:
            return False, "Device not found"

        if device.trust_status != DeviceStatus.TRUSTED:
            return False, f"Device not trusted: {device.trust_status.value}"

        if device.revoked_at:
            return False, "Device revoked"

        # Verify credential proof
        # In a real implementation, this would verify HMAC or signature
        # For now, we'll use a simple verification against stored credential
        credential = await repo.get_active_credential(device_id)
        if not credential:
            return False, "No active credential"

        # Verify the proof matches (simplified - in production use proper HMAC verification)
        # For now, we'll just check if the proof matches the stored hash
        import hashlib
        proof_hash = hashlib.sha256(credential_proof.encode()).hexdigest()
        if proof_hash != credential.credential_hash:
            # Log security event
            logger.warning("Invalid credential proof", extra={"device_id": str(device_id)})
            return False, "Invalid credential"

    return True, None
