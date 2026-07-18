from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.audit.models import AuditAction, AuditCategory
from app.audit.service import AuditService
from app.cache import valkey_client
from app.database.session import get_db_session_context as get_db_session
from app.emergency_stop.models import EmergencyStop
from app.events import subjects
from app.events.nats_client import nats_client


class EmergencyStopService:
    def __init__(self):
        pass

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

    async def activate(
        self, owner_id: UUID, reason: str, actor_id: UUID
    ) -> Optional[EmergencyStop]:
        async with get_db_session() as session:
            existing = await session.execute(
                select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
            )
            emergency_stop = existing.scalar_one_or_none()

            if emergency_stop:
                if emergency_stop.active:
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

            # Transition all existing QUEUED or APPROVED commands for this owner to blocked_by_emergency_stop
            from app.commands.models import Command, CommandState
            from app.commands.state_machine import transition_command
            from app.devices.models import Device

            dev_ids_query = select(Device.id).where(Device.owner_id == owner_id)
            dev_ids_result = await session.execute(dev_ids_query)
            dev_ids = dev_ids_result.scalars().all()

            if dev_ids:
                cmd_query = select(Command.id).where(
                    Command.device_id.in_(dev_ids),
                    Command.state.in_([CommandState.QUEUED.value, CommandState.APPROVED.value]),
                )
                cmd_result = await session.execute(cmd_query)
                cmd_ids = cmd_result.scalars().all()
                for cmd_id in cmd_ids:
                    try:
                        await transition_command(
                            session,
                            cmd_id,
                            CommandState.BLOCKED_BY_EMERGENCY_STOP,
                            "emergency_stop_activation",
                        )
                    except Exception:
                        pass

            audit = AuditService()
            await audit.create_audit_log(
                category=AuditCategory.EMERGENCY_STOP,
                action=AuditAction.EMERGENCY_STOP_ACTIVATED,
                result="success",
                user_id=actor_id,
                metadata={"reason": reason, "owner_id": str(owner_id)},
            )

            await session.commit()
            await session.refresh(emergency_stop)

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

            await nats_client.publish_js(
                subjects.emergency_stop(str(owner_id)),
                {
                    "owner_id": str(owner_id),
                    "active": True,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                message_id=f"estop-{owner_id}-{datetime.now(timezone.utc).timestamp()}",
            )

            return emergency_stop

    async def release(self, owner_id: UUID, released_by: UUID) -> Optional[EmergencyStop]:
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
            )
            emergency_stop = result.scalar_one_or_none()

            if not emergency_stop or not emergency_stop.active:
                return None

            emergency_stop.active = False
            emergency_stop.released_at = datetime.now(timezone.utc)
            emergency_stop.released_by = released_by

            await session.flush()

            audit = AuditService()
            await audit.create_audit_log(
                category=AuditCategory.EMERGENCY_STOP,
                action=AuditAction.EMERGENCY_STOP_RELEASED,
                result="success",
                user_id=released_by,
                metadata={"owner_id": str(owner_id)},
            )

            await session.commit()
            await session.refresh(emergency_stop)

            await valkey_client.delete(f"emergency_stop:{owner_id}")

            await nats_client.publish_js(
                subjects.emergency_resume(str(owner_id)),
                {
                    "owner_id": str(owner_id),
                    "active": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                message_id=f"eresume-{owner_id}-{datetime.now(timezone.utc).timestamp()}",
            )

            return emergency_stop

    async def get_status(self, owner_id: UUID) -> Optional[EmergencyStop]:
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
            )
            return result.scalar_one_or_none()
