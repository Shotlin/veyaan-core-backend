"""
Approval service.

GAP-P0-5: The `decide_approval` method now runs approval decision AND command
state transition in a SINGLE database session/transaction to guarantee atomicity.
No cross-session calls to CommandService that would open a second session.

GAP-P0-6: After transitioning approved command to QUEUED, an outbox event is
written in the same transaction so the command will be picked up and published
to NATS by the outbox publisher worker.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.api.errors import ApiError, ErrorCode
from app.approvals.models import Approval, ApprovalStatus
from app.approvals.repository import ApprovalRepository
from app.commands.models import Command, CommandState
from app.commands.registry import command_registry
from app.commands.state_machine import StateTransitionError, transition_command
from app.database.session import get_db_session_context as get_db_session
from app.events import subjects
from app.events.outbox import OutboxRepository


class ApprovalService:
    def __init__(self):
        pass

    async def create_approval(
        self,
        command_id: UUID,
        owner_id: UUID,
        action_title: str,
        action_description: str,
        expires_in_minutes: int = 30,
    ) -> tuple[Optional[Approval], Optional[str]]:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)

            # Load command in the SAME session (no cross-session call)
            result = await session.execute(select(Command).where(Command.id == command_id))
            command = result.scalar_one_or_none()
            if not command:
                return None, None

            # Verify ownership via device join
            from app.devices.models import Device

            dev_result = await session.execute(select(Device).where(Device.id == command.device_id))
            device = dev_result.scalar_one_or_none()
            if not device or str(device.owner_id) != str(owner_id):
                return None, None

            if command.state != CommandState.AWAITING_APPROVAL.value:
                return None, None

            # Use server registry risk level, not client-provided
            definition = command_registry.get(command.command_type)
            risk_level = definition.risk_level.value if definition else "medium"

            approval, decision_nonce = await repo.create_approval(
                command_id=command_id,
                owner_id=owner_id,
                risk_level=risk_level,
                action_title=action_title or f"Approve {command.command_type}",
                action_description=action_description
                or f"Approve command {command.command_type} for device {command.device_id}",
                expires_in_minutes=expires_in_minutes,
            )

            await session.commit()
            return approval, decision_nonce

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

    async def get_approval(self, approval_id: UUID) -> Optional[Approval]:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)
            return await repo.get_approval(approval_id)

    async def decide_approval(
        self,
        approval_id: UUID,
        owner_id: UUID,
        decision: str,
        nonce: str,
        note: Optional[str] = None,
    ) -> dict:
        """
        GAP-P0-5: Entire decision is atomic — approval status update, command
        state transition (APPROVED → QUEUED), and outbox event all commit
        in one database transaction.
        """
        import hashlib
        import hmac

        from app.audit.models import AuditAction, AuditCategory, AuditLog

        async with get_db_session() as session:
            repo = ApprovalRepository(session)

            approval = await repo.get_approval(approval_id)
            if not approval or str(approval.owner_id) != str(owner_id):
                return None

            if approval.status != ApprovalStatus.PENDING:
                raise ApiError(
                    ErrorCode.APPROVAL_ALREADY_DECIDED,
                    f"Approval already {approval.status.value}",
                    status_code=400,
                )

            if approval.expires_at and approval.expires_at < datetime.now(timezone.utc):
                approval.status = ApprovalStatus.EXPIRED
                await session.flush()
                await session.commit()
                raise ApiError(ErrorCode.APPROVAL_EXPIRED, "Approval has expired", status_code=400)

            # Verify nonce using hmac.compare_digest (no mock bypass in production)
            nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
            if not hmac.compare_digest(nonce_hash, approval.decision_nonce_hash):
                raise ApiError(
                    ErrorCode.INVALID_DECISION_NONCE, "Invalid decision nonce", status_code=400
                )

            # Update approval
            approval.status = (
                ApprovalStatus.APPROVED if decision == "approve" else ApprovalStatus.REJECTED
            )
            approval.decided_at = datetime.now(timezone.utc)
            approval.decision_note = note
            await session.flush()

            if approval.status == ApprovalStatus.APPROVED:
                # GAP-P0-4: Check emergency stop before queueing
                from app.emergency_stop.service import EmergencyStopService

                estop_service = EmergencyStopService()
                if await estop_service.is_active(owner_id):
                    raise ApiError(
                        ErrorCode.EMERGENCY_STOP_ACTIVE,
                        "Emergency stop is active. Cannot queue commands.",
                        status_code=423,
                    )

                # GAP-P0-5 + GAP-P0-6: Transition AND write outbox in same session
                try:
                    await transition_command(
                        session, approval.command_id, CommandState.APPROVED, "approval"
                    )
                    await transition_command(
                        session, approval.command_id, CommandState.QUEUED, "approval"
                    )
                except StateTransitionError as e:
                    raise ApiError(ErrorCode.INVALID_STATE, str(e), status_code=409) from e

                # GAP-P0-6: Write outbox event so outbox publisher will push to NATS
                cmd_result = await session.execute(
                    select(Command).where(Command.id == approval.command_id)
                )
                command = cmd_result.scalar_one_or_none()
                if command:
                    from app.devices.models import Device

                    dev_result = await session.execute(
                        select(Device).where(Device.id == command.device_id)
                    )
                    device = dev_result.scalar_one_or_none()
                    if device:
                        outbox_repo = OutboxRepository(session)
                        await outbox_repo.add_event(
                            event_type="command.queued",
                            aggregate_type="command",
                            aggregate_id=str(command.id),
                            subject=subjects.command_ready(str(device.id)),
                            payload={
                                "command_id": str(command.id),
                                "device_id": str(device.id),
                                "command_type": command.command_type,
                                "parameters": command.parameters,
                                "expires_at": command.expires_at.isoformat()
                                if command.expires_at
                                else None,
                                "risk_level": command.risk_level,
                            },
                        )

            elif approval.status == ApprovalStatus.REJECTED:
                try:
                    await transition_command(
                        session, approval.command_id, CommandState.REJECTED, "approval"
                    )
                except StateTransitionError as e:
                    raise ApiError(ErrorCode.INVALID_STATE, str(e), status_code=409) from e

            # Write AuditLog in the same transaction
            audit_log = AuditLog(
                user_id=owner_id,
                approval_id=approval.id,
                command_id=approval.command_id,
                category=AuditCategory.APPROVAL.value,
                action=(
                    AuditAction.APPROVAL_APPROVED.value
                    if decision == "approve"
                    else AuditAction.APPROVAL_REJECTED.value
                ),
                result="success",
                event_metadata={"note": note} if note else None,
            )
            add_res = session.add(audit_log)
            import asyncio

            if asyncio.iscoroutine(add_res):
                await add_res

            # Single commit for entire decision
            await session.commit()

            return {
                "approval_id": approval.id,
                "status": approval.status.value,
                "decided_at": approval.decided_at,
            }

    async def expire_pending_approvals(self) -> int:
        async with get_db_session() as session:
            repo = ApprovalRepository(session)
            count = await repo.expire_pending_approvals()
            await session.commit()
            return count
