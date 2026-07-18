"""Outbox publisher worker for reliable event publishing."""

import asyncio
import json
import logging
from typing import Optional

from app.events.nats_client import nats_client
from app.events.outbox import OutboxRepository
from app.database.session import get_db_session
from app.events.nats_client import nats_client
from app.config import settings
from app.database.session import get_db_session

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self):
        self.running = False
        self.interval = 5  # seconds
        self.batch_size = 100

    async def start(self):
        """Start the outbox publisher."""
        self.running = True
        logger.info("Starting outbox publisher")
        while self.running:
            try:
                await self.process_batch()
            except Exception as e:
                logger.exception("Outbox publisher error", error=str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        """Stop the outbox publisher."""
        self.running = False

    async def process_batch(self) -> int:
        """Process a batch of unpublished outbox events."""
        async with get_db_session() as session:
            repo = OutboxRepository(session)
            events = await repo.get_unpublished(limit=self.batch_size)

            if not events:
                return 0

            published = 0
            for event in events:
                try:
                    subject = self._get_subject_for_event(event.event_type)
                    await nats_client.publish(
                        subject,
                        json.dumps(event.payload).encode(),
                        headers={"Nats-Msg-Id": str(event.id)}
                    )
                    await self._mark_published(session, event.id)
                    published += 1
                except Exception as e:
                    logger.warning("Failed to publish outbox event", event_id=str(event.id), error=str(e))
                    await self._increment_attempt(session, event.id, str(e))

            if published > 0:
                await session.commit()

            return published

    def _get_subject_for_event(self, event_type: str) -> str:
        """Map event type to NATS subject."""
        mapping = {
            "command.queued": "veyaan.commands.ready",
            "command.cancelled": "veyaan.commands.cancel",
            "approval.created": "veyaan.approvals.created",
            "approval.decided": "veyaan.approvals.decided",
            "emergency_stop.activated": "veyaan.system.emergency_stop",
            "emergency_stop.released": "veyaan.system.emergency_stop_released",
            "device.revoked": "veyaan.device.revoked",
        }
        return mapping.get(event_type, f"veyaan.events.{event_type}")

    async def _mark_published(self, session, event_id):
        from app.events.outbox import OutboxRepository
        repo = OutboxRepository(session)
        await repo.mark_published(event_id)

    async def _increment_attempt(self, session, event_id, error: str):
        from app.events.outbox import OutboxRepository
        repo = OutboxRepository(session)
        await repo.increment_attempt(event_id, str(error))


async def main():
    """Main entry point for outbox publisher worker."""
    import logging
    logging.basicConfig(level=logging.INFO)

    from app.cache import valkey_client
    from app.database.connection import close_db, init_db
    from app.events.nats_client import nats_client
    from app.config import settings

    await init_db()
    await valkey_client.connect()

    nats_client.nc = await nats.connect(settings.NATS_URL)
    nats_client.js = nats_client.nc.jetstream()

    publisher = OutboxPublisher()
    try:
        await publisher.start()
    finally:
        await nats_client.disconnect()
        await close_db()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())