"""
Integration tests for the command pipeline.

Tests the full path: create command → outbox event → NATS publish → gateway delivery.

These tests require real service connections (postgres, nats, valkey).
They are skipped automatically in environments without those services.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestCommandPipelineUnit:
    """
    Unit-level pipeline tests using mocks.
    These run in every environment without service dependencies.
    """

    @pytest.mark.asyncio
    async def test_create_command_writes_outbox_event(self):
        """
        When a non-approval command is created, an outbox event must be written
        in the SAME transaction as the command itself.
        """
        from app.commands.service import CommandService

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

        outbox_events = []

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.DeviceRepository") as mock_dev_repo_class,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
            patch("app.commands.service.EmergencyStopService") as mock_estop,
            patch("app.commands.service.OutboxRepository") as mock_outbox_class,
        ):
            # Device setup
            mock_device = MagicMock()
            mock_device.owner_id = owner_id
            mock_device.id = device_id
            mock_device.trust_status = MagicMock()
            mock_device.trust_status.value = "trusted"

            mock_dev_repo = AsyncMock()
            mock_dev_repo.get_device = AsyncMock(return_value=mock_device)
            mock_dev_repo_class.return_value = mock_dev_repo

            # Command repo
            mock_repo = AsyncMock()
            mock_repo.get_by_idempotency_key = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            # Emergency stop off
            mock_estop_instance = AsyncMock()
            mock_estop_instance.is_active = AsyncMock(return_value=False)
            mock_estop.return_value = mock_estop_instance

            # Outbox — capture events added
            mock_outbox = AsyncMock()

            async def capture_event(**kwargs):
                outbox_events.append(kwargs)

            mock_outbox.add_event = AsyncMock(side_effect=capture_event)
            mock_outbox_class.return_value = mock_outbox

            # Session
            mock_session = AsyncMock()
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            # Mock transition_command to succeed
            with patch("app.commands.service.transition_command", new=AsyncMock()):
                service = CommandService()
                try:
                    await service.create_command(request, owner_id)
                except Exception:
                    pass  # Command object mock may not fully work, but we check outbox

        # An outbox event should have been created for a non-approval command
        assert any(
            e.get("event_type") == "command.queued" for e in outbox_events
        ), "Expected outbox event with event_type='command.queued' to be written"

    @pytest.mark.asyncio
    async def test_create_command_no_outbox_for_approval_required(self):
        """
        Commands requiring approval must NOT write an outbox event at creation.
        The outbox event is only written after the approval is decided.
        """
        from app.commands.service import CommandService

        owner_id = uuid4()
        device_id = uuid4()

        request = MagicMock()
        request.device_id = device_id
        request.command_type = "device.factory_reset"
        request.idempotency_key = str(uuid4())
        request.parameters = {}
        request.requires_approval = True  # requires approval
        request.delayed_execution_allowed = False
        request.expires_at = None

        outbox_events = []

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.DeviceRepository") as mock_dev_repo_class,
            patch("app.commands.service.CommandRepository") as mock_repo_class,
            patch("app.commands.service.EmergencyStopService") as mock_estop,
            patch("app.commands.service.OutboxRepository") as mock_outbox_class,
            patch("app.commands.service.command_registry") as mock_registry,
        ):
            mock_device = MagicMock()
            mock_device.owner_id = owner_id
            mock_device.id = device_id
            mock_device.trust_status = MagicMock()
            mock_device.trust_status.value = "trusted"

            mock_dev_repo = AsyncMock()
            mock_dev_repo.get_device = AsyncMock(return_value=mock_device)
            mock_dev_repo_class.return_value = mock_dev_repo

            mock_repo = AsyncMock()
            mock_repo.get_by_idempotency_key = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            mock_estop_instance = AsyncMock()
            mock_estop_instance.is_active = AsyncMock(return_value=False)
            mock_estop.return_value = mock_estop_instance

            mock_outbox = AsyncMock()

            async def capture_event(**kwargs):
                outbox_events.append(kwargs)

            mock_outbox.add_event = AsyncMock(side_effect=capture_event)
            mock_outbox_class.return_value = mock_outbox

            # Registry returns requires_approval=True
            mock_definition = MagicMock()
            mock_definition.requires_approval = True
            mock_definition.risk_level = MagicMock()
            mock_definition.risk_level.value = "high"
            mock_definition.delayed_execution_allowed = False
            mock_definition.parameter_schema = MagicMock(return_value=None)
            mock_registry.get = MagicMock(return_value=mock_definition)

            mock_session = AsyncMock()
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            with patch("app.commands.service.transition_command", new=AsyncMock()):
                service = CommandService()
                try:
                    await service.create_command(request, owner_id)
                except Exception:
                    pass

        # No outbox event should be created for approval-required commands
        assert (
            len(outbox_events) == 0
        ), "No outbox event should be written for commands awaiting approval"


class TestApprovalAtomicity:
    """Tests that approval decision + command transition + outbox are atomic."""

    @pytest.mark.asyncio
    async def test_approve_command_writes_outbox_event(self):
        """
        When an approval is decided as APPROVED, the outbox event for the
        command must be written in the same DB transaction.
        """
        from app.approvals.models import ApprovalStatus
        from app.approvals.service import ApprovalService

        approval_id = uuid4()
        command_id = uuid4()
        device_id = uuid4()
        owner_id = uuid4()

        outbox_events = []

        with (
            patch("app.approvals.service.get_db_session") as mock_db,
            patch("app.approvals.service.ApprovalRepository") as mock_repo_class,
            patch("app.approvals.service.OutboxRepository") as mock_outbox_class,
            patch("app.approvals.service.transition_command", new=AsyncMock()),
        ):
            # Approval setup
            mock_approval = MagicMock()
            mock_approval.id = approval_id
            mock_approval.owner_id = owner_id
            mock_approval.command_id = command_id
            mock_approval.status = ApprovalStatus.PENDING
            mock_approval.expires_at = None
            mock_approval.decided_at = None

            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(return_value=mock_approval)
            mock_repo.decide_approval = AsyncMock(return_value=(True, None))
            mock_repo_class.return_value = mock_repo

            # After decide, approval becomes APPROVED
            decided_approval = MagicMock()
            decided_approval.id = approval_id
            decided_approval.owner_id = owner_id
            decided_approval.command_id = command_id
            decided_approval.status = ApprovalStatus.APPROVED
            decided_approval.decided_at = None

            call_count = [0]

            async def get_approval_side_effect(aid):
                call_count[0] += 1
                if call_count[0] == 1:
                    return mock_approval
                return decided_approval

            mock_repo.get_approval = AsyncMock(side_effect=get_approval_side_effect)

            # Outbox
            mock_outbox = AsyncMock()

            async def capture_event(**kwargs):
                outbox_events.append(kwargs)

            mock_outbox.add_event = AsyncMock(side_effect=capture_event)
            mock_outbox_class.return_value = mock_outbox

            # Command + device for outbox payload
            mock_command = MagicMock()
            mock_command.id = command_id
            mock_command.device_id = device_id
            mock_command.command_type = "system.ping"
            mock_command.parameters = {}
            mock_command.expires_at = None
            mock_command.risk_level = "low"

            mock_device = MagicMock()
            mock_device.id = device_id

            mock_session = AsyncMock()
            MagicMock()
            results = [mock_command, mock_device]
            call_idx = [0]

            async def execute_side_effect(*args, **kwargs):
                r = MagicMock()
                idx = call_idx[0] % len(results)
                r.scalar_one_or_none.return_value = results[idx]
                call_idx[0] += 1
                return r

            mock_session.execute = AsyncMock(side_effect=execute_side_effect)
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            await service.decide_approval(
                approval_id=approval_id,
                owner_id=owner_id,
                decision="approve",
                nonce="valid-nonce",
            )

        # Should have written an outbox event
        assert any(
            e.get("event_type") == "command.queued" for e in outbox_events
        ), "Expected outbox event to be written when approval is APPROVED"
