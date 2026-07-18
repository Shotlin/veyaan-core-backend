"""Command consumer worker for processing commands from NATS."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.cache import valkey_client
from app.commands.models import Command
from app.commands.repository import CommandRepository
from app.commands.service import CommandService
from app.config import settings
from app.database.session import get_db_session
from app.events.nats_client import nats_client
from app.websocket.gateway import connection_manager

import nats
import json
import logging

logger = logging.getLogger(__name__)


class CommandConsumer:
    def __init__(self):
        self.running = False
        self.subscription = None

    async def start(self):
        """Start the command consumer."""
        self.running = True
        logger.info("Starting command consumer")

        # Subscribe to command delivery subject
        self.subscription = await nats_client.subscribe(
            "veyaan.commands.ready",
            durable=settings.NATS_CONSUMER_GATEWAY,
            stream=settings.NATS_STREAM_COMMANDS
        )

        logger.info("Command consumer started")

        while self.running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.exception("Command consumer error", error=str(e))
            await asyncio.sleep(1)

    def stop(self):
        """Stop the command consumer."""
        self.running = False

    async def _process_batch(self):
        """Process a batch of commands from NATS."""
        messages = await self.subscription.fetch(batch=10, timeout=1)

        for msg in messages:
            try:
                await self._handle_message(msg)
                await msg.ack()
            except Exception as e:
                logger.exception("Failed to process command", error=str(e))
                await msg.nak()

    async def _handle_message(self, msg):
        """Handle a single command message."""
        payload = json.loads(msg.data.decode())

        command_id = payload["command_id"]
        device_id = payload["device_id"]
        command_type = payload["command_type"]
        parameters = payload["parameters"]
        expires_at = payload.get("expires_at")
        risk_level = payload["risk_level"]
        trace_id = payload.get("trace_id")

        logger.info("Processing command", command_id=command_id, device_id=device_id, type=command_type)

        async with get_db_session() as session:
            repo = CommandRepository(session)

            # Get the command from database
            command = await repo.get_by_id(command_id)
            if not command:
                logger.warning("Command not found", command_id=command_id)
                return

            # Check if command has expired
            if expires_at and datetime.fromisoformat(expires_at).replace(tzinfo=None) < datetime.now(timezone.utc):
                await session.execute(
                    Command.__table__.update()
                    .where(Command.id == command_id)
                    .values(state="expired")
                )
                await session.commit()
                logger.warning("Command expired", command_id=command_id)
                return

            # Check if device is connected
            if not connection_manager.is_connected(device_id):
                logger.warning("Device not connected, command will be queued", device_id=device_id)
                # Command will be retried when device connects
                return

            # Update state to DELIVERED
            await session.execute(
                Command.__table__.update()
                .where(Command.id == command_id)
                .values(state="delivered", delivered_at=datetime.now(timezone.utc))
            )
            await session.flush()

            # Send command to device via WebSocket
            from app.websocket.protocol.messages import CommandRequestMessage

            command_msg = CommandRequestMessage(
                command_id=command_id,
                command_type=command_type,
                parameters=parameters,
                expires_at=expires_at,
                risk_metadata={"level": risk_level},
                trace_id=trace_id
            )

            sent = await connection_manager.send_command(device_id, command_msg)
            if not sent:
                logger.warning("Failed to deliver command, device may have disconnected", device_id=device_id)
                # Re-queue for later delivery
                return

            await session.commit()
            logger.info("Command delivered", command_id=command_id, device_id=device_id)


async def main():
    """Main entry point for command consumer worker."""
    import logging
    logging.basicConfig(level=logging.INFO)

    from app.cache import valkey_client
    from app.config import settings
    from app.database.connection import close_db, init_db
    from app.events.nats_client import nats_client

    await init_db()
    await valkey_client.connect()

    nats_client.nc = await nats.connect(settings.NATS_URL)
    nats_client.js = nats_client.nc.jetstream()

    consumer = CommandConsumer()
    try:
        await consumer.start()
    finally:
        await nats_client.disconnect()
        await close_db()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())