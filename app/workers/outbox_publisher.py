"""Outbox publisher worker for reliable event publishing."""

import asyncio
import logging

from app.database.connection import close_db, init_db
from app.database.session import get_db_session_context as get_db_session
from app.events.nats_client import nats_client
from app.events.outbox import OutboxRepository

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self):
        self.running = False
        self.interval = 5
        self.batch_size = 100

    async def start(self):
        self.running = True
        logger.info("Starting outbox publisher")
        while self.running:
            try:
                await self.process_batch()
            except Exception as e:
                logger.exception("Outbox publisher error", error=str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False

    async def process_batch(self) -> int:
        async with get_db_session() as session:
            repo = OutboxRepository(session)
            events = await repo.get_unpublished(limit=self.batch_size)

            if not events:
                return 0

            published = 0
            for event in events:
                try:
                    await nats_client.publish_js(
                        event.subject,
                        event.payload,
                        message_id=str(event.id),
                        headers=event.headers,
                    )
                    await repo.mark_published(event.id)
                    published += 1
                except Exception as e:
                    logger.warning("Failed to publish outbox event", event_id=str(event.id), error=str(e))
                    attempt_count = event.attempt_count or 0
                    if attempt_count >= 3:
                        await repo.mark_failed(event.id, str(e))
                    else:
                        await repo.increment_attempt(event.id, str(e))

            if published > 0:
                await session.commit()

            return published


async def main():
    logging.basicConfig(level=logging.INFO)

    from app.cache import valkey_client

    await init_db()
    await valkey_client.connect()
    await nats_client.connect()

    publisher = OutboxPublisher()
    try:
        await publisher.start()
    except KeyboardInterrupt:
        pass
    finally:
        await nats_client.disconnect()
        await valkey_client.disconnect()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
