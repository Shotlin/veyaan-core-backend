"""Notification service — GAP-P1-11.

Emits internal notification events and tracks delivery status.
In Project 1, push notification adapters (Firebase, APNS) are stubbed —
the service records events but does not require production push credentials.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import NotificationRecord


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: UUID,
        notification_type: str,
        channel: str = "internal",
        payload: Optional[dict] = None,
    ) -> NotificationRecord:
        """Create a new notification record in PENDING status."""
        record = NotificationRecord(
            user_id=user_id,
            notification_type=notification_type,
            channel=channel,
            status="pending",
            payload=payload or {},
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def mark_delivered(self, notification_id: UUID) -> bool:
        result = await self.session.execute(
            update(NotificationRecord)
            .where(NotificationRecord.id == notification_id)
            .values(status="delivered", delivered_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0

    async def mark_failed(self, notification_id: UUID, error: str) -> bool:
        result = await self.session.execute(
            update(NotificationRecord)
            .where(NotificationRecord.id == notification_id)
            .values(status="failed", error_message=str(error)[:500])
        )
        return result.rowcount > 0

    async def list_for_user(
        self,
        user_id: UUID,
        notification_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[NotificationRecord], int]:
        query = (
            select(NotificationRecord)
            .where(NotificationRecord.user_id == user_id)
            .order_by(NotificationRecord.created_at.desc())
        )
        if notification_type:
            query = query.where(NotificationRecord.notification_type == notification_type)

        count_result = await self.session.execute(
            select(NotificationRecord.id).where(NotificationRecord.user_id == user_id)
        )
        total = len(count_result.scalars().all())

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total
