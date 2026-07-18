import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.cache import valkey_client
from app.database.session import get_db_session
from app.devices.models import Device, DeviceStatus
from app.devices.repository import DeviceRepository
from app.events.nats_client import nats_client
from app.websocket.protocol.messages import (
    CommandAckMessage,
    CommandProgressMessage,
    CommandResultMessage,
    DeviceStatusUpdateMessage,
    EmergencyStopMessage,
    HeartbeatMessage,
    HelloMessage,
    WelcomeMessage,
)
from app.websocket.protocol.validator import ProtocolError, ProtocolValidator

logger = logging.getLogger(__name__)


class WebSocketHandler:
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager

    async def handle_message(self, device_id: UUID, raw_data: bytes) -> None:
        """Route incoming message to appropriate handler."""
        try:
            message = ProtocolValidator.parse_client_message(raw_data)
        except ProtocolError as e:
            logger.warning("protocol_error", device_id=str(device_id), code=e.code, message=e.message)
            await self.connection_manager.send_error(device_id, e.code, e.message)
            return

        handlers = {
            HelloMessage: self._handle_hello,
            HeartbeatMessage: self._handle_heartbeat,
            CommandAckMessage: self._handle_acknowledge,
            CommandProgressMessage: self._handle_progress,
            CommandResultMessage: self._handle_result,
            DeviceStatusUpdateMessage: self._handle_status_update,
        }

        handler = handlers.get(type(message))
        if handler:
            try:
                await handler(device_id, message)
            except Exception as e:
                logger.exception("handler_error", device_id=str(device_id), handler=type(message).__name__)
                await self.connection_manager.send_error(device_id, "HANDLER_ERROR", str(e))
        else:
            logger.warning("no_handler", device_id=str(device_id), message_type=type(message).__name__)

    async def _handle_hello(self, device_id: UUID, message: HelloMessage) -> None:
        """Handle initial hello/authentication from device."""
        logger.info("hello_received", device_id=str(device_id))

        # Verify device credentials
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            credential = await repo.get_active_credential(device_id)

        if not credential:
            raise ProtocolError("INVALID_CREDENTIAL", "Device not found or no valid credential")

        # Verify credential proof (HMAC of challenge)
        expected_proof = credential.credential_hash  # In practice, this would be HMAC verification
        if not self._verify_credential_proof(message.credential_proof, expected_proof):
            # Record security event
            await self._record_security_event(device_id, "invalid_credential_proof")
            raise ProtocolError("INVALID_CREDENTIAL", "Invalid device credential")

        # Check device trust status
        device = await self._get_device(device_id)
        if not device or device.trust_status != DeviceStatus.TRUSTED:
            raise ProtocolError("DEVICE_NOT_TRUSTED", "Device is not trusted or has been revoked")

        # Check protocol version
        ProtocolValidator.validate_protocol_version(message.protocol_version)

        # Check emergency stop
        emergency_stop = await self._is_emergency_stop_active(device_id)

        # Register connection
        connection_id = uuid4()
        await self.connection_manager.register_connection(
            device_id=device_id,
            connection_id=connection_id,
        )

        # Send welcome message
        welcome = WelcomeMessage(
            connection_id=connection_id,
            server_time=datetime.now(timezone.utc),
            heartbeat_interval=30,  # From config
            protocol_version="v1",
            emergency_stop_active=emergency_stop,
        )
        await self.connection_manager.send_message(device_id, welcome)

        # If emergency stop is active, also send stop message
        if emergency_stop:
            await self._send_emergency_stop(device_id, "Emergency stop active")

    async def _handle_heartbeat(self, device_id: UUID, message: HeartbeatMessage) -> None:
        """Handle heartbeat from device."""
        # Update presence in Valkey
        await valkey_client.set(
            f"device:presence:{device_id}",
            {
                "state": message.state,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "active_commands": message.active_command_count,
                "app_version": message.app_version,
            },
            ttl=90,  # 3x heartbeat interval
        )

        # Update device last_seen in database periodically
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            await repo.update_last_seen(device_id)

        # Check emergency stop
        if await self._is_emergency_stop_active(device_id):
            await self._send_emergency_stop(device_id, "Emergency stop active")

        # Respond with pong if needed (optional)

    async def _handle_acknowledge(self, device_id: UUID, message: CommandAckMessage) -> None:
        """Handle command acknowledgement from device."""
        logger.info("command_acknowledged", device_id=str(device_id), command_id=str(message.command_id), accepted=message.accepted)

        # Publish to NATS for command service
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.publish(
                "veyaan.commands.acknowledged",
                json.dumps({
                    "command_id": str(message.command_id),
                    "device_id": str(device_id),
                    "accepted": message.accepted,
                    "rejection_reason": message.rejection_reason,
                    "device_timestamp": message.device_timestamp.isoformat(),
                }).encode(),
            )

    async def _handle_progress(self, device_id: UUID, message: CommandProgressMessage) -> None:
        """Handle command progress update from device."""
        logger.debug("command_progress", device_id=str(device_id), command_id=str(message.command_id))

        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.publish(
                "veyaan.commands.progress",
                json.dumps({
                    "command_id": str(message.command_id),
                    "device_id": str(device_id),
                    "progress_percent": message.progress_percent,
                    "stage": message.stage,
                    "status_message": message.status_message,
                }).encode(),
            )

    async def _handle_result(self, device_id: UUID, message: CommandResultMessage) -> None:
        """Handle command result from device."""
        logger.info("command_result", device_id=str(device_id), command_id=str(message.command_id), success=message.success)

        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.publish(
                "veyaan.commands.result",
                json.dumps({
                    "command_id": str(message.command_id),
                    "device_id": str(device_id),
                    "success": message.success,
                    "result_data": message.result_data,
                    "error_code": message.error_code,
                    "error_message": message.error_message,
                    "started_at": message.started_at.isoformat(),
                    "finished_at": message.finished_at.isoformat(),
                }).encode(),
            )

    async def _handle_status_update(self, device_id: UUID, message: DeviceStatusUpdateMessage) -> None:
        """Handle device status update."""
        logger.info("device_status_update", device_id=str(device_id), state=message.state)

        await valkey_client.set(
            f"device:presence:{device_id}",
            {
                "state": message.state,
                "last_update": datetime.now(timezone.utc).isoformat(),
                "metadata": message.metadata,
            },
            ttl=90,
        )

        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.publish(
                "veyaan.device.status",
                json.dumps({
                    "device_id": str(device_id),
                    "state": message.state,
                    "metadata": message.metadata,
                }).encode(),
            )

    def _verify_credential_proof(self, proof: str, expected: str) -> bool:
        """Verify device credential proof (HMAC)."""
        # In production, this would verify HMAC(proof, challenge)
        # For now, do simple comparison
        return hmac.compare_digest(proof, expected)

    async def _get_device(self, device_id: UUID) -> Optional[Device]:
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            return await repo.get_device(device_id)

    async def _is_emergency_stop_active(self, device_id: UUID) -> bool:
        """Check if emergency stop is active for device's owner."""
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            device = await repo.get_device(device_id)
            if not device:
                return False
            # Check emergency stop from valkey cache
            cached = await valkey_client.get(f"emergency_stop:{device.owner_id}")
            if cached:
                return cached.get("active", False)
        return False

    async def _send_emergency_stop(self, device_id: UUID, reason: str) -> None:
        """Send emergency stop message to device."""
        msg = EmergencyStopMessage(reason=reason)
        await self.connection_manager.send_message(device_id, msg)

    async def _record_security_event(self, device_id: UUID, event_type: str) -> None:
        """Record security event to NATS."""
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.publish(
                "veyaan.security.events",
                json.dumps({
                    "device_id": str(device_id),
                    "event_type": event_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }).encode(),
            )
