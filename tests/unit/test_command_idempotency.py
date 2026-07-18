"""Unit tests for command idempotency behavior."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.errors import ApiError


class TestCommandIdempotency:
    def _make_request(self, command_type: str = "system.ping", idempotency_key: str = None):
        req = MagicMock()
        req.device_id = uuid4()
        req.command_type = command_type
        req.idempotency_key = idempotency_key or str(uuid4())
        req.parameters = {}
        req.requires_approval = False
        req.delayed_execution_allowed = False
        req.expires_at = None
        return req

    def _make_existing_command(self, command_type: str = "system.ping"):
        cmd = MagicMock()
        cmd.id = uuid4()
        cmd.command_type = command_type
        cmd.state = "queued"
        cmd.requires_approval = False
        return cmd

    @pytest.mark.asyncio
    async def test_same_key_same_type_returns_existing_command(self):
        from app.commands.service import CommandService

        owner_id = uuid4()
        key = "idempotency-key-123"
        request = self._make_request("system.ping", key)
        existing = self._make_existing_command("system.ping")

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.DeviceRepository") as mock_dev_repo_class,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
            patch("app.commands.service.EmergencyStopService") as mock_estop,
        ):
            mock_device = MagicMock()
            mock_device.owner_id = owner_id
            mock_device.trust_status = MagicMock()
            mock_device.trust_status.value = "trusted"

            mock_dev_repo = AsyncMock()
            mock_dev_repo.get_device = AsyncMock(return_value=mock_device)
            mock_dev_repo_class.return_value = mock_dev_repo

            mock_repo = AsyncMock()
            mock_repo.get_by_idempotency_key = AsyncMock(return_value=existing)
            mock_repo.get_task = AsyncMock(return_value=MagicMock(id=uuid4()))
            mock_repo_class.return_value = mock_repo

            mock_estop_instance = AsyncMock()
            mock_estop_instance.is_active = AsyncMock(return_value=False)
            mock_estop.return_value = mock_estop_instance

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = CommandService()
            response = await service.create_command(request, owner_id)

        assert str(response.command_id) == str(existing.id)

    @pytest.mark.asyncio
    async def test_same_key_different_type_raises_409_conflict(self):
        from app.commands.service import CommandService

        owner_id = uuid4()
        key = "idempotency-key-123"
        request = self._make_request("system.ping", key)
        # Existing command has DIFFERENT type
        existing = self._make_existing_command("device.get_status")

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.DeviceRepository") as mock_dev_repo_class,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
            patch("app.commands.service.EmergencyStopService") as mock_estop,
        ):
            mock_device = MagicMock()
            mock_device.owner_id = owner_id
            mock_device.trust_status = MagicMock()
            mock_device.trust_status.value = "trusted"

            mock_dev_repo = AsyncMock()
            mock_dev_repo.get_device = AsyncMock(return_value=mock_device)
            mock_dev_repo_class.return_value = mock_dev_repo

            mock_repo = AsyncMock()
            mock_repo.get_by_idempotency_key = AsyncMock(return_value=existing)
            mock_repo_class.return_value = mock_repo

            mock_estop_instance = AsyncMock()
            mock_estop_instance.is_active = AsyncMock(return_value=False)
            mock_estop.return_value = mock_estop_instance

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = CommandService()
            with pytest.raises(ApiError) as exc_info:
                await service.create_command(request, owner_id)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_emergency_stop_active_blocks_command(self):
        from app.commands.service import CommandService

        owner_id = uuid4()
        request = self._make_request()

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.DeviceRepository") as mock_dev_repo_class,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
            patch("app.commands.service.EmergencyStopService") as mock_estop,
        ):
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

        assert exc_info.value.status_code == 423  # Locked
