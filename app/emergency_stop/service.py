from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.cache import valkey_client
from app.database.session import get_db_session
from app.emergency_stop.models import EmergencyStop
from app.events.nats_client import nats_client


class EmergencyStopService:
    def __init__(self):
        pass

    async def is_active(self, user_id: UUID) -> bool:
        """Check if emergency stop is active for user."""
        # Check Valkey cache first
        cached = await valkey_client.get(f"emergency_stop:{user_id}")
        if cached:
            return cached.get("active", False)

        # Fallback to database
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.user_id == user_id)
            )
            emergency_stop = result.scalar_one_or_none()
            if emergency_stop and emergency_stop.active:
                # Cache for 60 seconds
                await valkey_client.set(
                    f"emergency_stop:{user_id}",
                    {"active": True, "activated_at": emergency_stop.activated_at.isoformat()},
                    ttl=60,
                )
                return True
        return False

    async def activate(self, user_id: UUID, reason: str) -> EmergencyStop:
        """Activate emergency stop for user."""
        async with get_db_session() as session:
            # Check if already active
            existing = await session.execute(
                select(EmergencyStop).where(EmergencyStop.user_id == user_id)
            )
            emergency_stop = existing.scalar_one_or_none()

            if emergency_stop:
                if emergency_stop.active:
                    return emergency_stop
                emergency_stop.active = True
                emergency_stop.reason = reason
                emergency_stop.activated_at = datetime.now(timezone.utc)
                emergency_stop.released_at = None
                emergency_stop.released_by = None
            else:
                emergency_stop = EmergencyStop(
                    user_id=user_id,
                    active=True,
                    reason=reason,
                    activated_at=datetime.now(timezone.utc),
                )
                session.add(emergency_stop)

            await session.commit()
            await session.refresh(emergency_stop)

            # Update cache
            await valkey_client.set(
                f"emergency_stop:{user_id}",
                {"active": True, "activated_at": emergency_stop.activated_at.isoformat()},
                ttl=3600,  # 1 hour
            )

            # Publish event to NATS
            await self._publish_emergency_stop_event(user_id, True, reason)

            return emergency_stop

    async def release(self, user_id: UUID, released_by: UUID) -> Optional[EmergencyStop]:
        """Release emergency stop for user."""
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.user_id == user_id)
            )
            emergency_stop = result.scalar_one_or_none()

            if not emergency_stop or not emergency_stop.active:
                return None

            emergency_stop.active = False
            emergency_stop.released_at = datetime.now(timezone.utc)
            emergency_stop.released_by = released_by

            await session.commit()
            await session.refresh(emergency_stop)

            # Update cache
            await valkey_client.delete(f"emergency_stop:{user_id}")

            # Publish event
            await self._publish_emergency_stop_event(user_id, False, "Emergency stop released")

            return emergency_stop

    async def get_status(self, user_id: UUID) -> Optional[EmergencyStop]:
        """Get emergency stop status."""
        async with get_db_session() as session:
            result = await session.execute(
                select(EmergencyStop).where(EmergencyStop.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def _publish_emergency_stop_event(self, user_id: UUID, active: bool, reason: str):
        """Publish emergency stop event to NATS."""
        import json

        payload = {
            "user_id": str(user_id),
            "active": active,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await nats_client.publish(
            "veyaan.system.emergency_stop",
            json.dumps(payload).encode(),
            headers={"user_id": str(user_id)},
        )
