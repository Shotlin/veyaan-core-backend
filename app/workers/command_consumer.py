"""Command lifecycle consumer worker."""

import asyncio
import json
import logging

from app.cache import valkey_client
from app.commands.models import CommandState, TaskState
from app.commands.service import TaskService
from app.commands.state_machine import transition_command
from app.config import settings
from app.database.connection import close_db, init_db
from app.database.session import get_db_session_context as get_db_session
from app.events.nats_client import nats_client

logger = logging.getLogger(__name__)


class CommandLifecycleConsumer:
    def __init__(self):
        self.running = False
        self.subscription = None

    async def start(self):
        self.running = True
        logger.info("Starting command lifecycle consumer")

        sub = await nats_client.subscribe_durable(
            "veyaan.command.result.>",
            durable_name="api_result_consumer",
            stream=settings.NATS_STREAM_COMMANDS,
        )

        logger.info("Command lifecycle consumer started")

        while self.running:
            try:
                msgs = await sub.fetch(batch=10, timeout=1)
                for msg in msgs:
                    try:
                        await self._handle_message(msg)
                        await msg.ack()
                    except Exception as e:
                        logger.exception("Failed to process message", error=str(e))
                        await msg.nak()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if "connection closed" in str(e).lower():
                    break
                logger.exception("Consumer error", error=str(e))
                await asyncio.sleep(1)

    def stop(self):
        self.running = False

    async def _handle_message(self, msg):
        from app.commands.repository import CommandRepository

        payload = json.loads(msg.data.decode())
        subject = msg.subject

        command_id = payload.get("command_id")

        if not command_id:
            logger.warning("No command_id in message")
            return

        async with get_db_session() as session:
            cmd_repo = CommandRepository(session)
            command = await cmd_repo.get_by_id(command_id)
            if not command:
                logger.warning("Command not found", command_id=command_id)
                return

            if "result" in subject:
                success = payload.get("success", False)
                if success:
                    await transition_command(
                        session, command_id, CommandState.SUCCEEDED, "device",
                        metadata={
                            "result_data": payload.get("result_data"),
                            "result_summary": "success" if success else "failed",
                        },
                    )
                else:
                    await transition_command(
                        session, command_id, CommandState.FAILED, "device",
                        metadata={
                            "error_code": payload.get("error_code"),
                            "error_message": payload.get("error_message"),
                        },
                    )

                task_service = TaskService()
                task = await task_service.get_task_by_command(command_id)
                if task:
                    new_state = TaskState.SUCCEEDED if success else TaskState.FAILED
                    await task_service.update_task_state(
                        task.id, new_state,
                        result_summary="success" if success else "failed",
                        error_code=payload.get("error_code"),
                        error_message=payload.get("error_message"),
                    )

            elif "acknowledged" in subject:
                accepted = payload.get("accepted", True)
                if accepted:
                    await transition_command(session, command_id, CommandState.ACKNOWLEDGED, "device")
                else:
                    await transition_command(session, command_id, CommandState.FAILED, "device",
                                             metadata={"error_message": payload.get("rejection_reason")})

            elif "progress" in subject:
                if command.state == CommandState.ACKNOWLEDGED.value:
                    await transition_command(session, command_id, CommandState.RUNNING, "device")

            await session.commit()


async def main():
    logging.basicConfig(level=logging.INFO)

    await init_db()
    await valkey_client.connect()
    await nats_client.connect()

    consumer = CommandLifecycleConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        pass
    finally:
        await nats_client.disconnect()
        await valkey_client.disconnect()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
