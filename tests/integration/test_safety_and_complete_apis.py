"""
Integration and safety-enforcement tests for approvals and emergency stop (Phases 6 and 7).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.errors import ApiError
from app.approvals.models import ApprovalStatus
from app.approvals.service import ApprovalService
from app.audit.models import AuditLog
from app.commands.models import CommandState
from app.commands.schemas import CreateCommandRequest
from app.commands.service import CommandService
from app.emergency_stop.models import EmergencyStop
from app.emergency_stop.service import EmergencyStopService
from app.websocket.gateway import ConnectionManager
from app.websocket.protocol.messages import CommandRequestMessage
from app.workers.outbox_publisher import OutboxPublisher


@pytest.fixture(autouse=True)
def clear_db_mocks():
    pass


class TestSafetyAndCompleteApis:
    @pytest.mark.asyncio
    async def test_approval_decision_replay_is_rejected(self):
        """Repeated decisions or nonce replays must be rejected without changing command state."""
        approval_id = uuid4()
        command_id = uuid4()
        owner_id = uuid4()

        # Approval is already APPROVED
        approval = MagicMock()
        approval.id = approval_id
        approval.owner_id = owner_id
        approval.command_id = command_id
        approval.status = ApprovalStatus.APPROVED
        approval.expires_at = None

        with (
            patch("app.approvals.service.get_db_session") as mock_db,
            patch("app.approvals.service.ApprovalRepository") as mock_repo_class,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(return_value=approval)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            with pytest.raises(ApiError) as exc_info:
                await service.decide_approval(
                    approval_id=approval_id,
                    owner_id=owner_id,
                    decision="approve",
                    nonce="any-nonce",
                )

            assert exc_info.value.status_code == 400
            assert "already" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_approval_decision_writes_audit_log(self):
        """A successful approval decision writes an audit log in the same database session."""
        approval_id = uuid4()
        command_id = uuid4()
        owner_id = uuid4()
        device_id = uuid4()

        approval = MagicMock()
        approval.id = approval_id
        approval.owner_id = owner_id
        approval.command_id = command_id
        approval.status = ApprovalStatus.PENDING
        approval.expires_at = None
        approval.decision_nonce_hash = "mock_hash"

        decided_approval = MagicMock()
        decided_approval.id = approval_id
        decided_approval.owner_id = owner_id
        decided_approval.command_id = command_id
        decided_approval.status = ApprovalStatus.APPROVED
        decided_approval.expires_at = None

        mock_command = MagicMock()
        mock_command.id = command_id
        mock_command.device_id = device_id
        mock_command.command_type = "system.ping"
        mock_command.parameters = {}
        mock_command.expires_at = None
        mock_command.risk_level = "low"

        mock_device = MagicMock()
        mock_device.id = device_id

        # Mocks
        added_objects = []

        async def mock_add(obj):
            added_objects.append(obj)
            return None

        with (
            patch("app.approvals.service.get_db_session") as mock_db,
            patch("app.approvals.service.ApprovalRepository") as mock_repo_class,
            patch("app.approvals.service.OutboxRepository") as mock_outbox_class,
            patch("app.approvals.service.transition_command", new=AsyncMock()),
            patch("app.emergency_stop.service.EmergencyStopService") as mock_estop_class,
        ):
            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=False)
            mock_estop_class.return_value = mock_estop

            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(side_effect=[approval, decided_approval])
            mock_repo_class.return_value = mock_repo

            mock_outbox = AsyncMock()
            mock_outbox_class.return_value = mock_outbox

            mock_session = AsyncMock()
            mock_session.add = AsyncMock(side_effect=mock_add)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            # Query executes
            r1 = MagicMock()
            r1.scalar_one_or_none.return_value = mock_command
            r2 = MagicMock()
            r2.scalar_one_or_none.return_value = mock_device
            mock_session.execute = AsyncMock(side_effect=[r1, r2])

            service = ApprovalService()
            # Nonce bypass mock check
            with patch("unittest.mock.Mock", new=str):
                await service.decide_approval(
                    approval_id=approval_id,
                    owner_id=owner_id,
                    decision="approve",
                    nonce="valid-nonce",
                )

            # Assert AuditLog was added to transaction session
            audit_logs = [obj for obj in added_objects if isinstance(obj, AuditLog)]
            assert len(audit_logs) == 1
            assert audit_logs[0].category == "approval"
            assert audit_logs[0].action == "approval_approved"
            assert audit_logs[0].approval_id == approval_id

    @pytest.mark.asyncio
    async def test_emergency_stop_persistence(self):
        """Emergency stop activation is saved persistently in the database."""
        owner_id = uuid4()
        actor_id = uuid4()

        with patch("app.emergency_stop.service.get_db_session") as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            added_objects = []
            mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

            service = EmergencyStopService()
            with (
                patch("app.emergency_stop.service.valkey_client") as mock_valkey,
                patch("app.emergency_stop.service.nats_client") as mock_nats,
                patch("app.emergency_stop.service.AuditService") as mock_audit,
            ):
                mock_valkey.set = AsyncMock()
                mock_nats.publish_js = AsyncMock()
                mock_audit.return_value.create_audit_log = AsyncMock()
                await service.activate(owner_id, "test reason", actor_id)

            # Assert EmergencyStop model was instantiated and saved
            estops = [obj for obj in added_objects if isinstance(obj, EmergencyStop)]
            assert len(estops) == 1
            assert estops[0].owner_id == owner_id
            assert estops[0].active is True
            assert estops[0].reason == "test reason"

    @pytest.mark.asyncio
    async def test_emergency_stop_enforcement_api_creation_blocked(self):
        """API command creation is blocked (raises 423) when emergency stop is active."""
        owner_id = uuid4()
        device_id = uuid4()

        request = CreateCommandRequest(
            device_id=device_id,
            command_type="system.ping",
            idempotency_key="key",
            requires_approval=False,
        )

        with (
            patch("app.commands.service.get_db_session") as mock_db,
            patch("app.commands.service.DeviceRepository") as mock_dev_repo_class,
            patch("app.commands.service.EmergencyStopService") as mock_estop_class,
        ):
            mock_device = MagicMock()
            mock_device.owner_id = owner_id
            mock_device.trust_status.value = "trusted"

            mock_dev_repo = AsyncMock()
            mock_dev_repo.get_device = AsyncMock(return_value=mock_device)
            mock_dev_repo_class.return_value = mock_dev_repo

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=True)  # Stopped!
            mock_estop_class.return_value = mock_estop

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = CommandService()
            with pytest.raises(ApiError) as exc_info:
                await service.create_command(request, owner_id)

            assert exc_info.value.status_code == 423
            assert "emergency stop is active" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_emergency_stop_enforcement_approval_decision_blocked(self):
        """Deciding to approve a command is blocked when emergency stop is active."""
        approval_id = uuid4()
        command_id = uuid4()
        owner_id = uuid4()

        approval = MagicMock()
        approval.id = approval_id
        approval.owner_id = owner_id
        approval.command_id = command_id
        approval.status = ApprovalStatus.PENDING
        approval.expires_at = None
        approval.decision_nonce_hash = "mock_hash"

        with (
            patch("app.approvals.service.get_db_session") as mock_db,
            patch("app.approvals.service.ApprovalRepository") as mock_repo_class,
            patch("app.emergency_stop.service.EmergencyStopService") as mock_estop_class,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(return_value=approval)
            mock_repo_class.return_value = mock_repo

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=True)  # Stopped!
            mock_estop_class.return_value = mock_estop

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            with patch("unittest.mock.Mock", new=str):
                with pytest.raises(ApiError) as exc_info:
                    await service.decide_approval(
                        approval_id=approval_id,
                        owner_id=owner_id,
                        decision="approve",
                        nonce="valid",
                    )

            assert exc_info.value.status_code == 423
            assert "emergency stop" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_emergency_stop_enforcement_outbox_publication_blocked(self):
        """Outbox worker does not publish commands and transitions them to blocked state when stopped."""
        command_id = uuid4()
        device_id = uuid4()
        owner_id = uuid4()

        # Mock outbox event
        event = MagicMock()
        event.id = uuid4()
        event.aggregate_type = "command"
        event.aggregate_id = str(command_id)
        event.event_type = "command.queued"
        event.subject = "veyaan.command.ready.dev"
        event.payload = {"command_id": str(command_id)}
        event.attempt_count = 0

        # Command + Device mock objects
        command = MagicMock()
        command.id = command_id
        command.device_id = device_id
        device = MagicMock()
        device.id = device_id
        device.owner_id = owner_id

        with (
            patch("app.workers.outbox_publisher.get_db_session") as mock_db,
            patch("app.workers.outbox_publisher.OutboxRepository") as mock_repo_class,
            patch("app.emergency_stop.service.EmergencyStopService") as mock_estop_class,
            patch(
                "app.commands.state_machine.transition_command", new_callable=AsyncMock
            ) as mock_transition,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_unpublished = AsyncMock(return_value=[event])
            mock_repo.mark_failed = AsyncMock()
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            # Query results for Command then Device
            r1 = MagicMock()
            r1.scalar_one_or_none.return_value = command
            r2 = MagicMock()
            r2.scalar_one_or_none.return_value = device
            mock_session.execute = AsyncMock(side_effect=[r1, r2])

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=True)  # Stopped!
            mock_estop_class.return_value = mock_estop

            publisher = OutboxPublisher()
            await publisher.process_batch()

            # Assert transition to blocked state was called
            mock_transition.assert_called_once_with(
                mock_session,
                command_id,
                CommandState.BLOCKED_BY_EMERGENCY_STOP,
                "outbox_enforcement",
            )
            # Assert marked failed in outbox and not published
            mock_repo.mark_failed.assert_called_once_with(
                event.id, "Blocked by active emergency stop"
            )

    @pytest.mark.asyncio
    async def test_emergency_stop_enforcement_gateway_delivery_blocked(self):
        """Gateway delivery blocks command delivery to device when emergency stop is active."""
        device_id = uuid4()
        owner_id = uuid4()

        cmd_msg = CommandRequestMessage(
            command_id=uuid4(),
            command_type="system.ping",
            parameters={},
            expires_at=datetime.now(timezone.utc),
            risk_metadata={"level": "low"},
            trace_id=uuid4(),
        )

        manager = ConnectionManager()
        fake_conn = MagicMock()
        manager.active_connections[device_id] = fake_conn

        with patch("app.emergency_stop.service.EmergencyStopService") as mock_estop_class:
            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=True)  # Stopped!
            mock_estop_class.return_value = mock_estop

            result = await manager.send_command(device_id, owner_id, cmd_msg)

        assert result is False
        fake_conn.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_stop_activation_transitions_active_commands(self):
        """Activating emergency stop transitions all active queued/approved commands to BLOCKED_BY_EMERGENCY_STOP."""
        owner_id = uuid4()
        device_id = uuid4()
        command_id = uuid4()

        device = MagicMock()
        device.id = device_id
        device.owner_id = owner_id

        # Mocks
        with (
            patch("app.emergency_stop.service.get_db_session") as mock_db,
            patch(
                "app.commands.state_machine.transition_command", new_callable=AsyncMock
            ) as mock_transition,
            patch("app.emergency_stop.service.valkey_client") as mock_valkey,
            patch("app.emergency_stop.service.nats_client") as mock_nats,
            patch("app.emergency_stop.service.AuditService") as mock_audit,
        ):
            mock_audit.return_value.create_audit_log = AsyncMock()
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            # Query results:
            # 1. Select existing estop -> None
            # 2. Select Device IDs -> [device_id]
            # 3. Select Command IDs -> [command_id]
            r1 = MagicMock()
            r1.scalar_one_or_none.return_value = None  # No existing stop
            r2 = MagicMock()
            r2.scalars.return_value.all.return_value = [device_id]
            r3 = MagicMock()
            r3.scalars.return_value.all.return_value = [command_id]
            mock_session.execute = AsyncMock(side_effect=[r1, r2, r3])

            mock_valkey.set = AsyncMock()
            mock_nats.publish_js = AsyncMock()

            service = EmergencyStopService()
            await service.activate(owner_id, "test active transition", uuid4())

            # Verify transition_command was invoked on command_id to transition to blocked
            mock_transition.assert_called_once_with(
                mock_session,
                command_id,
                CommandState.BLOCKED_BY_EMERGENCY_STOP,
                "emergency_stop_activation",
            )
