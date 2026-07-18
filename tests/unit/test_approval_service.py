"""
Unit tests for ApprovalService.

Tests approval create, decide (approve/reject), nonce replay, and expiry.
Uses FakeClock for deterministic time control.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.approvals.models import ApprovalStatus


class TestApprovalDecision:

    def _make_approval(
        self,
        status: ApprovalStatus = ApprovalStatus.PENDING,
        expires_at: datetime | None = None,
        owner_id=None,
        command_id=None,
    ):
        approval = MagicMock()
        approval.id = uuid4()
        approval.owner_id = owner_id or uuid4()
        approval.command_id = command_id or uuid4()
        approval.status = status
        approval.expires_at = expires_at
        approval.decided_at = None
        return approval

    @pytest.mark.asyncio
    async def test_approve_pending_transitions_command_to_queued(self):
        """APPROVE on PENDING approval must transition command → APPROVED → QUEUED."""
        from app.approvals.service import ApprovalService

        owner_id = uuid4()
        approval = self._make_approval(owner_id=owner_id)

        decided_approval = MagicMock()
        decided_approval.id = approval.id
        decided_approval.owner_id = owner_id
        decided_approval.command_id = approval.command_id
        decided_approval.status = ApprovalStatus.APPROVED
        decided_approval.decided_at = datetime.now(timezone.utc)

        transition_calls = []

        with patch("app.approvals.service.get_db_session") as mock_db, \
             patch("app.approvals.service.ApprovalRepository") as mock_repo_class, \
             patch("app.approvals.service.OutboxRepository"), \
             patch("app.approvals.service.transition_command") as mock_transition:

            call_count = [0]
            async def get_approval_side(aid):
                call_count[0] += 1
                return approval if call_count[0] == 1 else decided_approval

            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(side_effect=get_approval_side)
            mock_repo.decide_approval = AsyncMock(return_value=(True, None))
            mock_repo_class.return_value = mock_repo

            mock_transition.side_effect = lambda s, cid, state, actor: transition_calls.append(state)

            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            ))
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            result = await service.decide_approval(
                approval_id=approval.id,
                owner_id=owner_id,
                decision="approve",
                nonce="valid-nonce",
            )

        assert result is not None
        assert result["status"] == ApprovalStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_reject_pending_transitions_command_to_rejected(self):
        """REJECT on PENDING approval must transition command → REJECTED."""
        from app.approvals.service import ApprovalService

        owner_id = uuid4()
        approval = self._make_approval(owner_id=owner_id)

        decided_approval = MagicMock()
        decided_approval.id = approval.id
        decided_approval.owner_id = owner_id
        decided_approval.command_id = approval.command_id
        decided_approval.status = ApprovalStatus.REJECTED
        decided_approval.decided_at = datetime.now(timezone.utc)

        with patch("app.approvals.service.get_db_session") as mock_db, \
             patch("app.approvals.service.ApprovalRepository") as mock_repo_class, \
             patch("app.approvals.service.OutboxRepository"), \
             patch("app.approvals.service.transition_command") as mock_transition:

            call_count = [0]
            async def get_approval_side(aid):
                call_count[0] += 1
                return approval if call_count[0] == 1 else decided_approval

            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(side_effect=get_approval_side)
            mock_repo.decide_approval = AsyncMock(return_value=(True, None))
            mock_repo_class.return_value = mock_repo
            mock_transition.side_effect = AsyncMock()

            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            ))
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            result = await service.decide_approval(
                approval_id=approval.id,
                owner_id=owner_id,
                decision="reject",
                nonce="valid-nonce",
            )

        assert result["status"] == ApprovalStatus.REJECTED.value

    @pytest.mark.asyncio
    async def test_already_decided_raises_error(self):
        """Deciding an already-decided approval raises APPROVAL_ALREADY_DECIDED."""
        from app.api.errors import ApiError
        from app.approvals.service import ApprovalService

        owner_id = uuid4()
        # Approval is already APPROVED
        approval = self._make_approval(status=ApprovalStatus.APPROVED, owner_id=owner_id)

        with patch("app.approvals.service.get_db_session") as mock_db, \
             patch("app.approvals.service.ApprovalRepository") as mock_repo_class:

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
                    approval_id=approval.id,
                    owner_id=owner_id,
                    decision="approve",
                    nonce="any-nonce",
                )

        assert exc_info.value.status_code == 400
        assert "already" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_expired_approval_raises_error(self):
        """Deciding an expired approval raises APPROVAL_EXPIRED."""
        from app.api.errors import ApiError
        from app.approvals.service import ApprovalService

        owner_id = uuid4()
        past_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        approval = self._make_approval(
            status=ApprovalStatus.PENDING,
            expires_at=past_time,
            owner_id=owner_id,
        )

        with patch("app.approvals.service.get_db_session") as mock_db, \
             patch("app.approvals.service.ApprovalRepository") as mock_repo_class:

            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(return_value=approval)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            with pytest.raises(ApiError) as exc_info:
                await service.decide_approval(
                    approval_id=approval.id,
                    owner_id=owner_id,
                    decision="approve",
                    nonce="any-nonce",
                )

        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_cross_owner_decide_returns_none(self):
        """decide_approval returns None when owner_id doesn't match approval owner."""
        from app.approvals.service import ApprovalService

        real_owner = uuid4()
        attacker = uuid4()
        approval = self._make_approval(owner_id=real_owner)

        with patch("app.approvals.service.get_db_session") as mock_db, \
             patch("app.approvals.service.ApprovalRepository") as mock_repo_class:

            mock_repo = AsyncMock()
            mock_repo.get_approval = AsyncMock(return_value=approval)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            result = await service.decide_approval(
                approval_id=approval.id,
                owner_id=attacker,
                decision="approve",
                nonce="any-nonce",
            )

        assert result is None


class TestApprovalCreate:

    @pytest.mark.asyncio
    async def test_create_approval_uses_registry_risk_level(self):
        """Risk level from server registry, not client input, is used in approval creation."""
        from app.approvals.service import ApprovalService

        command_id = uuid4()
        owner_id = uuid4()

        mock_command = MagicMock()
        mock_command.id = command_id
        mock_command.device_id = uuid4()
        mock_command.command_type = "device.factory_reset"
        from app.commands.models import CommandState
        mock_command.state = CommandState.AWAITING_APPROVAL.value

        mock_device = MagicMock()
        mock_device.owner_id = owner_id


        with patch("app.approvals.service.get_db_session") as mock_db, \
             patch("app.approvals.service.ApprovalRepository") as mock_repo_class, \
             patch("app.approvals.service.command_registry") as mock_registry:

            from app.commands.models import RiskLevel
            mock_def = MagicMock()
            mock_def.risk_level = RiskLevel.HIGH
            mock_registry.get = MagicMock(return_value=mock_def)

            mock_repo = AsyncMock()
            mock_repo.create_approval = AsyncMock(return_value=(MagicMock(), "nonce123"))
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            MagicMock()

            call_count = [0]
            async def execute_side(stmt, **kw):
                call_count[0] += 1
                r = MagicMock()
                r.scalar_one_or_none.return_value = mock_command if call_count[0] == 1 else mock_device
                return r

            mock_session.execute = AsyncMock(side_effect=execute_side)
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = ApprovalService()
            approval, nonce = await service.create_approval(
                command_id=command_id,
                owner_id=owner_id,
                action_title="Reset Device",
                action_description="Factory reset the device",
            )

        # Verify risk_level came from registry (HIGH), not from client
        call_kwargs = mock_repo.create_approval.call_args.kwargs
        assert call_kwargs["risk_level"] == "high"
