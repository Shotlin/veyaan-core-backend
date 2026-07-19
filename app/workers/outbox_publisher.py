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
                    # Enforce Emergency Stop check before publishing a command ready event (Enforcement Point 3)
                    if event.aggregate_type == "command" and "queued" in event.event_type:
                        from sqlalchemy import select

                        from app.commands.models import Command, CommandState
                        from app.commands.state_machine import transition_command
                        from app.devices.models import Device
                        from app.emergency_stop.service import EmergencyStopService

                        cmd_id = event.aggregate_id
                        cmd_result = await session.execute(
                            select(Command).where(Command.id == cmd_id)
                        )
                        command = cmd_result.scalar_one_or_none()
                        if command:
                            dev_result = await session.execute(
                                select(Device).where(Device.id == command.device_id)
                            )
                            device = dev_result.scalar_one_or_none()
                            if device:
                                estop_service = EmergencyStopService()
                                if await estop_service.is_active(device.owner_id):
                                    try:
                                        await transition_command(
                                            session,
                                            command.id,
                                            CommandState.BLOCKED_BY_EMERGENCY_STOP,
                                            "outbox_enforcement",
                                        )
                                    except Exception as e:
                                        logger.warning(
                                            "outbox_emergency_stop_block_failed",
                                            command_id=str(command.id),
                                            event_id=str(event.id),
                                            error=str(e),
                                        )
                                    await repo.mark_failed(
                                        event.id, "Blocked by active emergency stop"
                                    )
                                    continue

                    await nats_client.publish_js(
                        event.subject,
                        event.payload,
                        message_id=str(event.id),
                        headers=event.headers,
                    )
                    await repo.mark_published(event.id)
                    published += 1
                except Exception as e:
                    logger.warning(
                        "Failed to publish outbox event", event_id=str(event.id), error=str(e)
                    )
                    attempt_count = event.attempt_count or 0
                    if attempt_count >= 3:
                        await repo.mark_failed(event.id, str(e))
                    else:
                        await repo.increment_attempt(event.id, str(e))

            if published > 0 or len(events) > 0:
                # Always commit after processing a batch — marks state changes durable
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
