"""
Cross-owner security tests.

Verifies that users cannot access or modify resources owned by other users.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestCrossOwnerIsolation:
    @pytest.mark.asyncio
    async def test_user_cannot_cancel_another_users_command(self):
        """cancel_command must return False when owner_id doesn't match."""
        from app.commands.service import CommandService

        user_a = uuid4()
        user_b = uuid4()
        command_id = uuid4()

        # Command belongs to user_b's device
        mock_command = MagicMock()
        mock_device = MagicMock()
        mock_device.owner_id = user_b
        mock_command.device = mock_device

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_command)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = CommandService()
            # User A tries to cancel User B's command
            result = await service.cancel_command(command_id, user_a)

        assert result is False, "User A should not be able to cancel User B's command"

    @pytest.mark.asyncio
    async def test_user_cannot_revoke_another_users_device(self):
        """revoke_device must fail if device belongs to a different owner."""
        from app.devices.service import DeviceService

        user_a = uuid4()
        uuid4()
        device_id = uuid4()

        with (
            patch("app.devices.service.get_db_session") as mock_db,
            patch("app.devices.service.DeviceRepository") as mock_repo_class,
        ):
            mock_repo = AsyncMock()
            # revoke returns False when owner doesn't match
            mock_repo.revoke_device = AsyncMock(return_value=False)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = DeviceService()
            result = await service.revoke_device(device_id, user_a)

        assert result is False

    @pytest.mark.asyncio
    async def test_user_cannot_get_state_events_of_another_users_command(self):
        """get_state_events returns empty list for cross-owner access."""
        from app.commands.service import CommandService

        user_a = uuid4()
        user_b = uuid4()
        command_id = uuid4()

        # Command belongs to user_b
        mock_command = MagicMock()
        mock_device = MagicMock()
        mock_device.owner_id = user_b
        mock_command.device = mock_device

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_command)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = CommandService()
            events = await service.get_state_events(command_id, user_a)

        assert events == [], "Cross-owner state events must return empty list"

    @pytest.mark.asyncio
    async def test_user_cannot_decide_another_users_approval(self):
        """decide_approval returns None when owner_id doesn't match."""
        from app.approvals.service import ApprovalService

        user_a = uuid4()
        user_b = uuid4()
        approval_id = uuid4()

        # Approval belongs to user_b
        mock_approval = MagicMock()
        mock_approval.owner_id = user_b

        with (
            patch("app.approvals.service.get_db_session") as mock_db,
            patch("app.approvals.service.ApprovalRepository") as mock_repo_class,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(return_value=mock_approval)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            result = await service.decide_approval(
                approval_id=approval_id,
                owner_id=user_a,
                decision="approve",
                nonce="any",
            )

        assert result is None, "Cross-owner approval decision must return None"

    @pytest.mark.asyncio
    async def test_websocket_rejects_command_ack_for_wrong_device(self):
        """
        _command_belongs_to_device must return False when the command
        belongs to a different device.
        """
        from app.websocket.gateway import _command_belongs_to_device

        command_id = uuid4()
        device_a = uuid4()
        device_b = uuid4()

        with patch("app.websocket.gateway.get_db_session") as mock_db:
            mock_session = AsyncMock()
            result_mock = MagicMock()
            # Command belongs to device_b
            result_mock.scalar_one_or_none.return_value = device_b
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            # device_a claims ownership — must be rejected
            result = await _command_belongs_to_device(command_id, device_a)

        assert result is False

    @pytest.mark.asyncio
    async def test_websocket_accepts_command_ack_for_correct_device(self):
        """
        _command_belongs_to_device must return True when command belongs to device.
        """
        from app.websocket.gateway import _command_belongs_to_device

        command_id = uuid4()
        device_id = uuid4()

        with patch("app.websocket.gateway.get_db_session") as mock_db:
            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = device_id
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            result = await _command_belongs_to_device(command_id, device_id)

        assert result is True
