from typing import Optional
from uuid import UUID

from app.approvals.models import Approval, ApprovalStatus
from app.approvals.repository import ApprovalRepository
from app.approvals.schemas import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
)
from app.commands.models import CommandState
from app.commands.service import CommandService
from app.database.session import get_db_session


class ApprovalService:
    def __init__(self):
        pass

    async def create_approval(
        self,
        request: ApprovalCreateRequest,
        owner_id: UUID,
    ) -> tuple[ApprovalDecisionResponse, str]:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)
            command_service = CommandService()

            command = await command_service.get_command(request.command_id)
            if not command:
                raise ValueError("Command not found")

            if command.state != CommandState.AWAITING_APPROVAL:
                raise ValueError(f"Command is not awaiting approval (current state: {command.state.value})")

            if str(command.device.owner_id) != str(owner_id):
                raise ValueError("Not authorized")

            approval, decision_nonce = await repo.create_approval(
                command_id=request.command_id,
                owner_id=owner_id,
                risk_level=request.risk_level.value,
                action_title=request.action_title,
                action_description=request.action_description,
                expires_in_minutes=request.expires_in_minutes,
            )

            await session.commit()

            response = ApprovalDecisionResponse(
                approval_id=approval.id,
                status=ApprovalStatus.PENDING,
                decided_at=approval.decided_at,
            )

            return response, decision_nonce

    async def list_approvals(
        self,
        owner_id: UUID,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Approval], int]:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)
            return await repo.list_approvals(owner_id, status, risk_level, page, page_size)

    async def decide_approval(
        self,
        approval_id: UUID,
        owner_id: UUID,
        request: ApprovalDecisionRequest,
    ) -> ApprovalDecisionResponse:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)
            command_service = CommandService()

            success, error = await repo.decide_approval(
                approval_id=approval_id,
                owner_id=owner_id,
                decision=request.decision.value,
                nonce=request.nonce,
                note=request.note,
            )

            if not success:
                raise ValueError(error)

            approval = await repo.get_approval(approval_id)

            if approval.status == ApprovalStatus.APPROVED:
                await command_service.approve_command(approval.command_id)
            elif approval.status == ApprovalStatus.REJECTED:
                await command_service.reject_command(approval.command_id)

            await session.commit()

            return ApprovalDecisionResponse(
                approval_id=approval.id,
                status=approval.status,
                decided_at=approval.decided_at,
            )

    async def expire_pending_approvals(self) -> int:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)
            count = await repo.expire_pending_approvals()
            await session.commit()
            return count
