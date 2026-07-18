"""Scheduler worker for periodic maintenance tasks."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.approvals.repository import ApprovalRepository
from app.commands.models import Command, CommandState
from app.database.session import get_db_session_context as get_db_session
from app.devices.models import Device, DeviceStatus, PairingRequest, PairingStatus

logger = logging.getLogger(__name__)

# Devices whose heartbeat is older than this (seconds) are considered offline
STALE_DEVICE_HEARTBEAT_THRESHOLD = 120


class SchedulerWorker:
    def __init__(self):
        self.running = False
        self.interval = 30

    async def start(self):
        self.running = True
        logger.info("Starting scheduler worker")
        while self.running:
            try:
                await self.run_tasks()
            except Exception as e:
                logger.exception("Scheduler worker error", error=str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False
        logger.info("Stopping scheduler worker")

    async def run_tasks(self):
        async with get_db_session() as session:
            expired_pairings = await self._expire_stale_pairings(session)
            if expired_pairings:
                logger.info("Expired stale pairing requests", count=expired_pairings)

            expired_approvals = await self._expire_approvals(session)
            if expired_approvals:
                logger.info("Expired approval requests", count=expired_approvals)

            expired_commands = await self._expire_commands(session)
            if expired_commands:
                logger.info("Expired commands", count=expired_commands)

            await session.commit()

        # Stale presence detection runs against Valkey — separate from DB session
        stale_devices = await self._detect_stale_device_presence()
        if stale_devices:
            logger.info("Marked stale device presence", count=stale_devices)

    async def _expire_stale_pairings(self, session) -> int:
        result = await session.execute(
            update(PairingRequest)
            .where(
                PairingRequest.status == PairingStatus.PENDING,
                PairingRequest.expires_at < datetime.now(timezone.utc),
            )
            .values(status=PairingStatus.EXPIRED)
        )
        return result.rowcount

    async def _expire_approvals(self, session) -> int:
        repo = ApprovalRepository(session)
        return await repo.expire_pending_approvals()

    async def _expire_commands(self, session) -> int:
        non_terminal = [
            CommandState.QUEUED.value,
            CommandState.AWAITING_APPROVAL.value,
            CommandState.APPROVED.value,
            CommandState.DELIVERED.value,
        ]

        result = await session.execute(
            select(Command.id).where(
                Command.state.in_(non_terminal),
                Command.expires_at.is_not(None),
                Command.expires_at < datetime.now(timezone.utc),
            )
        )
        expired_ids = [row[0] for row in result.fetchall()]

        if expired_ids:
            await session.execute(
                update(Command)
                .where(Command.id.in_(expired_ids))
                .values(state=CommandState.EXPIRED.value, finished_at=datetime.now(timezone.utc))
            )
            return len(expired_ids)
        return 0

    async def _detect_stale_device_presence(self) -> int:
        """
        GAP-P1-13: Detect devices whose Valkey heartbeat key has expired
        (i.e. they stopped sending heartbeats) and update their last_seen_at
        in the DB so the UI reflects the correct offline state.

        A device presence key lives in Valkey with TTL=90s (set by gateway).
        When the TTL expires the device is considered offline.

        This task scans connected device records and checks for missing presence
        keys, then updates last_seen_at for audit purposes.
        """
        from app.cache import valkey_client
        from uuid import UUID

        stale_count = 0
        try:
            # Find all devices that have a connection record but no presence heartbeat
            async with get_db_session() as session:
                result = await session.execute(
                    select(Device.id).where(
                        Device.trust_status == DeviceStatus.TRUSTED,
                        Device.revoked_at.is_(None),
                    )
                )
                device_ids = [row[0] for row in result.fetchall()]

            stale_device_ids = []
            for device_id in device_ids:
                # Check if device has an active WebSocket connection registered
                connection_data = await valkey_client.get_hash(f"device:connection:{device_id}")
                if connection_data:
                    # Device was recently connected — check for heartbeat presence
                    presence = await valkey_client.get_hash(f"device:presence:{device_id}")
                    if not presence:
                        # Connection key exists but presence (heartbeat) has expired → stale
                        stale_device_ids.append(device_id)

            if stale_device_ids:
                now = datetime.now(timezone.utc)
                async with get_db_session() as session:
                    for device_id in stale_device_ids:
                        await session.execute(
                            update(Device)
                            .where(Device.id == device_id)
                            .values(last_seen_at=now)
                        )
                    await session.commit()
                stale_count = len(stale_device_ids)

        except Exception as e:
            logger.exception("Stale device presence detection failed", error=str(e))

        return stale_count


async def main():
    logging.basicConfig(level=logging.INFO)

    from app.cache import valkey_client
    from app.database.connection import close_db, init_db
    from app.events.nats_client import nats_client

    await init_db()
    await valkey_client.connect()
    await nats_client.connect()

    worker = SchedulerWorker()
    try:
        await worker.start()
    except KeyboardInterrupt:
        pass
    finally:
        await nats_client.disconnect()
        await valkey_client.disconnect()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())


logger = logging.getLogger(__name__)


class SchedulerWorker:
    def __init__(self):
        self.running = False
        self.interval = 30

    async def start(self):
        self.running = True
        logger.info("Starting scheduler worker")
        while self.running:
            try:
                await self.run_tasks()
            except Exception as e:
                logger.exception("Scheduler worker error", error=str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False
        logger.info("Stopping scheduler worker")

    async def run_tasks(self):
        async with get_db_session() as session:
            expired_pairings = await self._expire_stale_pairings(session)
            if expired_pairings:
                logger.info("Expired stale pairing requests", count=expired_pairings)

            expired_approvals = await self._expire_approvals(session)
            if expired_approvals:
                logger.info("Expired approval requests", count=expired_approvals)

            expired_commands = await self._expire_commands(session)
            if expired_commands:
                logger.info("Expired commands", count=expired_commands)

            await session.commit()

    async def _expire_stale_pairings(self, session):

        result = await session.execute(
            update(PairingRequest)
            .where(
                PairingRequest.status == PairingStatus.PENDING,
                PairingRequest.expires_at < datetime.now(timezone.utc),
            )
            .values(status=PairingStatus.EXPIRED)
        )
        return result.rowcount

    async def _expire_approvals(self, session):
        repo = ApprovalRepository(session)
        return await repo.expire_pending_approvals()

    async def _expire_commands(self, session):

        non_terminal = [
            CommandState.QUEUED.value,
            CommandState.AWAITING_APPROVAL.value,
            CommandState.APPROVED.value,
            CommandState.DELIVERED.value,
        ]

        result = await session.execute(
            select(Command.id).where(
                Command.state.in_(non_terminal),
                Command.expires_at.is_not(None),
                Command.expires_at < datetime.now(timezone.utc),
            )
        )
        expired_ids = [row[0] for row in result.fetchall()]

        if expired_ids:
            await session.execute(
                update(Command)
                .where(Command.id.in_(expired_ids))
                .values(state=CommandState.EXPIRED.value, finished_at=datetime.now(timezone.utc))
            )
            return len(expired_ids)
        return 0


async def main():
    logging.basicConfig(level=logging.INFO)

    from app.cache import valkey_client
    from app.database.connection import close_db, init_db
    from app.events.nats_client import nats_client

    await init_db()
    await valkey_client.connect()
    await nats_client.connect()

    worker = SchedulerWorker()
    try:
        await worker.start()
    except KeyboardInterrupt:
        pass
    finally:
        await nats_client.disconnect()
        await valkey_client.disconnect()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
