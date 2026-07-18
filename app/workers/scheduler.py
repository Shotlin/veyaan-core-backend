"""Scheduler worker for periodic maintenance tasks."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.approvals.repository import ApprovalRepository
from app.database.session import get_db_session
from app.devices.repository import DeviceRepository
from app.events.nats_client import nats_client

logger = logging.getLogger(__name__)


class SchedulerWorker:
    def __init__(self):
        self.running = False
        self.interval = 30  # seconds

    async def start(self):
        """Start the scheduler worker."""
        self.running = True
        logger.info("Starting scheduler worker")
        while self.running:
            try:
                await self.run_tasks()
            except Exception as e:
                logger.exception("Scheduler worker error", error=str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        """Stop the scheduler worker."""
        self.running = False
        logger.info("Stopping scheduler worker")

    async def run_tasks(self):
        """Run all scheduled tasks."""
        async with get_db_session() as session:
            # Expire stale pairing requests
            expired_pairings = await self._expire_stale_pairings(session)
            if expired_pairings:
                logger.info("Expired stale pairing requests", count=expired_pairings)

            # Expire approval requests
            expired_approvals = await self._expire_approvals(session)
            if expired_approvals:
                logger.info("Expired approval requests", count=expired_approvals)

            # Expire commands past deadline
            expired_commands = await self._expire_commands(session)
            if expired_commands:
                logger.info("Expired commands", count=expired_commands)

            # Detect stale device presence
            stale_devices = await self._detect_stale_devices(session)
            if stale_devices:
                logger.info("Detected stale devices", count=stale_devices)

            # Retry pending outbox events
            retried_outbox = await self._retry_outbox_events(session)
            if retried_outbox:
                logger.info("Retried outbox events", count=retried_outbox)

            await session.commit()

    async def _expire_stale_pairings(self, session) -> int:
        """Expire pairing requests past their expiration time."""
        from sqlalchemy import update

        from app.devices.models import PairingRequest

        result = await session.execute(
            update(PairingRequest)
            .where(
                PairingRequest.status == "pending",
                PairingRequest.expires_at < datetime.now(timezone.utc),
            )
            .values(status="expired")
        )
        return result.rowcount

    async def _expire_approvals(self, session) -> int:
        """Expire approval requests past their expiration time."""
        repo = ApprovalRepository(session)
        return await repo.expire_pending_approvals()

    async def _expire_commands(self, session) -> int:
        """Expire commands past their deadline."""
        from datetime import datetime, timezone

        from sqlalchemy import select, update

        from app.commands.models import Command

        # Find commands that have expired
        result = await session.execute(
            select(Command.id).where(
                Command.state.in_(["queued", "awaiting_approval"]),
                Command.expires_at.isnot(None),
                Command.expires_at < datetime.now(timezone.utc),
            )
        )
        expired_ids = [row[0] for row in result.fetchall()]

        if expired_ids:
            await session.execute(
                update(Command)
                .where(Command.id.in_(expired_ids))
                .values(state="expired")
            )
            return len(expired_ids)
        return 0

    async def _detect_stale_devices(self, session) -> int:
        """Mark devices as offline if they haven't sent heartbeat recently."""
        from datetime import datetime, timezone

        from app.devices.models import Device

        repo = DeviceRepository(session)
        # Devices that haven't sent heartbeat in 2x heartbeat interval (60s * 2 = 120s)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
        result = await session.execute(
            select(Device).where(
                Device.trust_status == "trusted",
                Device.last_seen_at.isnot(None),
                Device.last_seen_at < cutoff,
            )
        )
        stale_devices = result.scalars().all()

        count = 0
        for device in stale_devices:
            device.trust_status = "offline"
            count += 1

        return count

    async def _retry_outbox_events(self, session) -> int:
        """Retry pending outbox events."""

        from app.events.outbox import OutboxRepository

        repo = OutboxRepository(session)
        events = await repo.get_unpublished(limit=100)
        retried = 0

        for event in events:
            try:
                subject = self._get_subject_for_event(event.event_type)
                await nats_client.publish(
                    subject,
                    event.payload.encode(),
                    headers={"Nats-Msg-Id": str(event.id)}
                )
                await repo.mark_published(event.id)
                retried += 1
            except Exception as e:
                logger.warning("Failed to retry outbox event", event_id=str(event.id), error=str(e))
                await repo.increment_attempt(event.id, str(e))

        return retried

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


async def main():
    """Main entry point for scheduler worker."""
    import logging
    logging.basicConfig(level=logging.INFO)

    worker = SchedulerWorker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
