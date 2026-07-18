from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.outbox_models import OutboxEvent, OutboxEventStatus


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        subject: str,
        payload: dict,
        headers: dict = None,
    ):
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            subject=subject,
            payload=payload,
            headers=headers or {},
            status=OutboxEventStatus.PENDING,
            available_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def get_unpublished(self, limit: int = 100):
        result = await self.session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxEventStatus.PENDING)
            .where(OutboxEvent.available_at <= datetime.now(timezone.utc))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: UUID):
        result = await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status=OutboxEventStatus.PUBLISHED,
                published_at=datetime.now(timezone.utc),
            )
        )
        return result.rowcount > 0

    async def mark_failed(self, event_id: UUID, error: str):
        await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status=OutboxEventStatus.FAILED,
                last_error=str(error)[:1000],
            )
        )

    async def increment_attempt(self, event_id: UUID, error: str):
        await self.session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                attempt_count=OutboxEvent.attempt_count + 1,
                last_error=str(error)[:1000],
                status=OutboxEventStatus.PENDING,
            )
        )
