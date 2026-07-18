from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.emergency_stop.models import EmergencyStop


class EmergencyStopRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_emergency_stop(self, owner_id: UUID) -> Optional[EmergencyStop]:
        result = await self.session.execute(
            select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def activate_emergency_stop(
        self,
        owner_id: UUID,
        activated_by: UUID,
        reason: Optional[str] = None,
    ) -> EmergencyStop:
        existing = await self.get_emergency_stop(owner_id)
        if existing:
            existing.active = True
            existing.reason = reason
            existing.activated_at = datetime.now(timezone.utc)
            existing.activated_by = activated_by
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        emergency_stop = EmergencyStop(
            owner_id=owner_id,
            active=True,
            reason=reason,
            activated_at=datetime.now(timezone.utc),
            activated_by=activated_by,
        )
        self.session.add(emergency_stop)
        await self.session.flush()
        await self.session.refresh(emergency_stop)
        return emergency_stop

    async def release_emergency_stop(
        self,
        owner_id: UUID,
        released_by: UUID,
        reason: Optional[str] = None,
    ) -> Optional[EmergencyStop]:
        existing = await self.get_emergency_stop(owner_id)
        if not existing or not existing.active:
            return None

        existing.active = False
        existing.released_at = datetime.now(timezone.utc)
        existing.released_by = released_by
        if reason:
            existing.reason = reason
        existing.updated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(existing)
        return existing

    async def is_active(self, owner_id: UUID) -> bool:
        result = await self.session.execute(
            select(EmergencyStop.active).where(EmergencyStop.owner_id == owner_id)
        )
        active = result.scalar_one_or_none()
        return active is True
