import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.models import Approval, ApprovalStatus


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_approval(
        self,
        command_id: UUID,
        owner_id: UUID,
        risk_level: str,
        action_title: str,
        action_description: str,
        expires_in_minutes: int,
    ) -> tuple[Approval, str]:
        """Create an approval request. Returns (approval, decision_nonce)."""
        # Generate decision nonce
        decision_nonce = secrets.token_urlsafe(32)
        nonce_hash = hashlib.sha256(decision_nonce.encode()).hexdigest()

        approval = Approval(
            command_id=command_id,
            owner_id=owner_id,
            risk_level=risk_level,
            action_title=action_title,
            action_description=action_description,
            status=ApprovalStatus.PENDING,
            decision_nonce_hash=nonce_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
        )
        self.session.add(approval)
        await self.session.flush()
        await self.session.refresh(approval)
        return approval, decision_nonce

    async def get_approval(self, approval_id: UUID) -> Optional[Approval]:
        result = await self.session.execute(select(Approval).where(Approval.id == approval_id))
        return result.scalar_one_or_none()

    async def list_approvals(
        self,
        owner_id: UUID,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Approval], int]:
        query = select(Approval).where(Approval.owner_id == owner_id)

        if status:
            query = query.where(Approval.status == status)
        if risk_level:
            query = query.where(Approval.risk_level == risk_level)

        query = query.order_by(Approval.created_at.desc())

        # Count total
        count_query = select(Approval.id).where(Approval.owner_id == owner_id)
        if status:
            count_query = count_query.where(Approval.status == status)
        if risk_level:
            count_query = count_query.where(Approval.risk_level == risk_level)

        total_result = await self.session.execute(count_query)
        total = len(total_result.scalars().all())

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        approvals = list(result.scalars().all())

        return approvals, total

    async def decide_approval(
        self,
        approval_id: UUID,
        owner_id: UUID,
        decision: str,
        nonce: str,
        note: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """Decide an approval. Returns (success, error_message)."""
        approval = await self.get_approval(approval_id)
        if not approval:
            return False, "Approval not found"

        if str(approval.owner_id) != str(owner_id):
            return False, "Not authorized"

        if approval.status != ApprovalStatus.PENDING:
            return False, f"Approval already {approval.status.value}"

        if approval.expires_at < datetime.now(timezone.utc):
            approval.status = ApprovalStatus.EXPIRED
            await self.session.flush()
            return False, "Approval has expired"

        # Verify nonce
        nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        if not hashlib.compare_digest(nonce_hash, approval.decision_nonce_hash):
            return False, "Invalid decision nonce"

        # Update approval
        approval.status = (
            ApprovalStatus.APPROVED if decision == "approve" else ApprovalStatus.REJECTED
        )
        approval.decided_at = datetime.now(timezone.utc)
        approval.decision_note = note

        await self.session.flush()
        return True, None

    async def expire_pending_approvals(self) -> int:
        """Expire all pending approvals past their expiry. Returns count."""
        result = await self.session.execute(
            update(Approval)
            .where(
                Approval.status == ApprovalStatus.PENDING,
                Approval.expires_at < datetime.now(timezone.utc),
            )
            .values(status=ApprovalStatus.EXPIRED)
        )
        return result.rowcount
