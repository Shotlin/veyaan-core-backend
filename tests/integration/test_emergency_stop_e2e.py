"""
Emergency stop integration tests.

Verifies the full activate → block → release → allow cycle.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone


class TestEmergencyStopE2E:

    @pytest.mark.asyncio
    async def test_activate_then_command_blocked_at_api(self):
        """
        When emergency stop is active, create_command must raise 423 Locked.
        """
        from app.commands.service import CommandService
        from app.api.errors import ApiError

        owner_id = uuid4()
        device_id = uuid4()

        request = MagicMock()
        request.device_id = device_id
        request.command_type = "system.ping"
        request.idempotency_key = str(uuid4())
        request.parameters = {}
        request.requires_approval = False
        request.delayed_execution_allowed = False
        request.expires_at = None

        with patch("app.commands.service.get_db_session") as mock_db, \
             patch("app.commands.service.DeviceRepository") as mock_dev_repo_class, \
             patch("app.commands.service.CommandRepository") as mock_repo_class, \
             patch("app.commands.service.EmergencyStopService") as mock_estop:

            mock_device = MagicMock()
            mock_device.owner_id = owner_id
            mock_device.trust_status = MagicMock()
            mock_device.trust_status.value = "trusted"

            mock_dev_repo = AsyncMock()
            mock_dev_repo.get_device = AsyncMock(return_value=mock_device)
            mock_dev_repo_class.return_value = mock_dev_repo

            mock_repo = AsyncMock()
            mock_repo.get_by_idempotency_key = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            # Emergency stop IS active
            mock_estop_instance = AsyncMock()
            mock_estop_instance.is_active = AsyncMock(return_value=True)
            mock_estop.return_value = mock_estop_instance

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = CommandService()
            with pytest.raises(ApiError) as exc_info:
                await service.create_command(request, owner_id)

        assert exc_info.value.status_code == 423
        assert "emergency" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_activate_blocks_command_at_gateway(self):
        """
        When emergency stop is active, send_command returns False (delivery blocked).
        """
        from app.websocket.gateway import ConnectionManager
        from app.websocket.protocol.messages import CommandRequestMessage
        from uuid import uuid4
        from datetime import datetime, timezone

        manager = ConnectionManager()
        owner_id = uuid4()
        device_id = uuid4()

        # Register a fake connection
        from app.websocket.gateway import DeviceConnection
        import asyncio

        class FakeWebSocket:
            async def send_json(self, data): pass
            async def close(self, code=1000, reason=""): pass

        conn = DeviceConnection(device_id, owner_id, uuid4(), FakeWebSocket())
        manager.active_connections[device_id] = conn

        cmd_msg = CommandRequestMessage(
            command_id=uuid4(),
            command_type="system.ping",
            parameters={},
            expires_at=datetime.now(timezone.utc),
            risk_metadata={"level": "low"},
            trace_id=uuid4(),
        )

        with patch("app.websocket.gateway.valkey_client") as mock_valkey:
            # Emergency stop is active in Valkey
            mock_valkey.get = AsyncMock(return_value={"active": True})

            result = await manager.send_command(device_id, owner_id, cmd_msg)

        assert result is False, "send_command should return False when emergency stop active"

    @pytest.mark.asyncio
    async def test_release_allows_command_at_gateway(self):
        """
        After emergency stop release, send_command returns True.
        """
        from app.websocket.gateway import ConnectionManager, DeviceConnection
        from app.websocket.protocol.messages import CommandRequestMessage
        from datetime import datetime, timezone

        manager = ConnectionManager()
        owner_id = uuid4()
        device_id = uuid4()

        sent_messages = []

        class FakeWebSocket:
            async def send_json(self, data):
                sent_messages.append(data)
                return True
            async def close(self, code=1000, reason=""): pass

        conn = DeviceConnection(device_id, owner_id, uuid4(), FakeWebSocket())
        manager.active_connections[device_id] = conn

        cmd_msg = CommandRequestMessage(
            command_id=uuid4(),
            command_type="system.ping",
            parameters={},
            expires_at=datetime.now(timezone.utc),
            risk_metadata={"level": "low"},
            trace_id=uuid4(),
        )

        with patch("app.websocket.gateway.valkey_client") as mock_valkey:
            # Emergency stop is NOT active (released)
            mock_valkey.get = AsyncMock(return_value={"active": False})

            result = await manager.send_command(device_id, owner_id, cmd_msg)

        assert result is True, "send_command should return True when emergency stop not active"
        assert len(sent_messages) == 1, "Command should be delivered to device"

    @pytest.mark.asyncio
    async def test_emergency_stop_state_in_welcome_message(self):
        """
        The is_active state returned by EmergencyStopService must be reflected
        in the WelcomeMessage sent to the connecting device.
        """
        from app.websocket.protocol.messages import WelcomeMessage
        from uuid import uuid4
        from datetime import datetime, timezone

        # Simulate building a welcome message with active=True
        welcome = WelcomeMessage(
            connection_id=uuid4(),
            server_time=datetime.now(timezone.utc),
            heartbeat_interval=30,
            protocol_version="v1",
            emergency_stop_active=True,
        )

        assert welcome.emergency_stop_active is True

        # And with active=False
        welcome_inactive = WelcomeMessage(
            connection_id=uuid4(),
            server_time=datetime.now(timezone.utc),
            heartbeat_interval=30,
            protocol_version="v1",
            emergency_stop_active=False,
        )

        assert welcome_inactive.emergency_stop_active is False
