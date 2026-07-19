"""Emergency stop service.

Transaction boundaries
----------------------
All writes within activate() and release() commit in a SINGLE database
transaction that includes:

  - EmergencyStop row update
  - Command state transitions (QUEUED/APPROVED → BLOCKED_BY_EMERGENCY_STOP)
  - Audit row (AuditService receives the same session)
  - Outbox event (OutboxRepository receives the same session)

The outbox publisher delivers the NATS event after commit.
This makes emergency-stop activation durable even when NATS is temporarily
unavailable (P0-14 fix).

Valkey is updated as a cache AFTER the commit — it is not authoritative.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditAction, AuditCategory
from app.audit.service import AuditService
from app.cache import valkey_client
from app.database.session import get_db_session_context as get_db_session
from app.emergency_stop.models import EmergencyStop
from app.events import subjects
from app.events.outbox import OutboxRepository


class EmergencyStopService:
    def __init__(self) -> None:
        pass

    # ── Cache-first is_active check ───────────────────────────────────────────

    async def is_active(self, owner_id: UUID) -> bool:
        cached = await valkey_client.get(f"emergency_stop:{owner_id}")
        if cached is not None:
            if isinstance(cached, dict):
                return cached.get("active", False)
            return bool(cached)

        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
            )
            emergency_stop = result.scalar_one_or_none()
            if emergency_stop and emergency_stop.active:
                await valkey_client.set(
                    f"emergency_stop:{owner_id}",
                    {
                        "active": True,
                        "activated_at": emergency_stop.activated_at.isoformat()
                        if emergency_stop.activated_at
                        else None,
                    },
                    ttl=60,
                )
                return True
        return False

    # ── Activation ────────────────────────────────────────────────────────────

    async def activate(
        self, owner_id: UUID, reason: str, actor_id: UUID
    ) -> Optional[EmergencyStop]:
        """Activate emergency stop.

        All writes (stop row + blocked commands + audit + outbox) share
        one transaction.  Valkey cache is updated after commit.
        """
        from app.commands.models import Command, CommandState
        from app.commands.state_machine import transition_command
        from app.devices.models import Device

        async with get_db_session() as session:
            # Lock or create the owner emergency-stop row
            existing = await session.execute(
                select(EmergencyStop).where(EmergencyStop.owner_id == owner_id).with_for_update()
            )
            emergency_stop = existing.scalar_one_or_none()

            if emergency_stop:
                if emergency_stop.active:
                    # Already active — ensure at least one undelivered outbox event
                    # exists (idempotency: re-activation must re-notify the gateway)
                    outbox = OutboxRepository(session)
                    await outbox.add_event(
                        event_type="emergency_stop.activated",
                        aggregate_type="owner",
                        aggregate_id=str(owner_id),
                        subject=subjects.emergency_stop(str(owner_id)),
                        payload={
                            "owner_id": str(owner_id),
                            "active": True,
                            "reason": emergency_stop.reason,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    await session.commit()
                    return emergency_stop

                emergency_stop.active = True
                emergency_stop.reason = reason
                emergency_stop.activated_at = datetime.now(timezone.utc)
                emergency_stop.activated_by = actor_id
                emergency_stop.released_at = None
                emergency_stop.released_by = None
            else:
                emergency_stop = EmergencyStop(
                    owner_id=owner_id,
                    active=True,
                    reason=reason,
                    activated_at=datetime.now(timezone.utc),
                    activated_by=actor_id,
                )
                session.add(emergency_stop)

            await session.flush()

            # Block queued/approved commands for all owner devices
            await self._block_commands(session, owner_id, transition_command)

            # Audit row in the SAME transaction
            audit = AuditService(session)
            await audit.create_audit_log(
                category=AuditCategory.EMERGENCY_STOP,
                action=AuditAction.EMERGENCY_STOP_ACTIVATED,
                result="success",
                user_id=actor_id,
                metadata={"reason": reason, "owner_id": str(owner_id)},
            )

            # Outbox event in the SAME transaction (replaces direct NATS publish)
            outbox = OutboxRepository(session)
            await outbox.add_event(
                event_type="emergency_stop.activated",
                aggregate_type="owner",
                aggregate_id=str(owner_id),
                subject=subjects.emergency_stop(str(owner_id)),
                payload={
                    "owner_id": str(owner_id),
                    "active": True,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Single commit — stop row + commands + audit + outbox
            await session.commit()
            await session.refresh(emergency_stop)

        # Update Valkey cache AFTER commit (cache is not authoritative)
        await valkey_client.set(
            f"emergency_stop:{owner_id}",
            {
                "active": True,
                "activated_at": emergency_stop.activated_at.isoformat()
                if emergency_stop.activated_at
                else None,
            },
            ttl=3600,
        )

        return emergency_stop

    # ── Release ───────────────────────────────────────────────────────────────

    async def release(self, owner_id: UUID, released_by: UUID) -> Optional[EmergencyStop]:
        """Release emergency stop.

        Audit and outbox event share the same transaction.
        Blocked commands do NOT auto-resume; users must submit new commands.
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop)
                .where(EmergencyStop.owner_id == owner_id)
                .with_for_update()
            )
            emergency_stop = result.scalar_one_or_none()

            if not emergency_stop or not emergency_stop.active:
                return None

            emergency_stop.active = False
            emergency_stop.released_at = datetime.now(timezone.utc)
            emergency_stop.released_by = released_by

            await session.flush()

            # Audit row in the SAME transaction
            audit = AuditService(session)
            await audit.create_audit_log(
                category=AuditCategory.EMERGENCY_STOP,
                action=AuditAction.EMERGENCY_STOP_RELEASED,
                result="success",
                user_id=released_by,
                metadata={"owner_id": str(owner_id)},
            )

            # Outbox event in the SAME transaction (replaces direct NATS publish)
            outbox = OutboxRepository(session)
            await outbox.add_event(
                event_type="emergency_stop.released",
                aggregate_type="owner",
                aggregate_id=str(owner_id),
                subject=subjects.emergency_resume(str(owner_id)),
                payload={
                    "owner_id": str(owner_id),
                    "active": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Single commit — release + audit + outbox
            await session.commit()
            await session.refresh(emergency_stop)

        # Invalidate Valkey cache AFTER commit
        await valkey_client.delete(f"emergency_stop:{owner_id}")

        return emergency_stop

    # ── Status query ──────────────────────────────────────────────────────────

    async def get_status(self, owner_id: UUID) -> Optional[EmergencyStop]:
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
            )
            return result.scalar_one_or_none()

    # ── Helper ────────────────────────────────────────────────────────────────

    @staticmethod
    async def _block_commands(
        session: AsyncSession,
        owner_id: UUID,
        transition_command,
    ) -> None:
        """Transition QUEUED and APPROVED commands to BLOCKED_BY_EMERGENCY_STOP.

        Uses the same session as the outer transaction.
        Failures per command are logged but do not abort the outer transaction.
        """
        from app.commands.models import Command, CommandState
        from app.devices.models import Device
        from app.observability.logging import logger

        dev_ids_result = await session.execute(
            select(Device.id).where(Device.owner_id == owner_id)
        )
        dev_ids = dev_ids_result.scalars().all()

        if not dev_ids:
            return

        cmd_result = await session.execute(
            select(Command.id).where(
                Command.device_id.in_(dev_ids),
                Command.state.in_([CommandState.QUEUED.value, CommandState.APPROVED.value]),
            )
        )
        cmd_ids = cmd_result.scalars().all()

        for cmd_id in cmd_ids:
            try:
                await transition_command(
                    session,
                    cmd_id,
                    CommandState.BLOCKED_BY_EMERGENCY_STOP,
                    "emergency_stop_activation",
                )
            except Exception as exc:
                logger.warning(
                    "failed_to_block_command",
                    command_id=str(cmd_id),
                    error=str(exc),
                )
