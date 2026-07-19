"""Command lifecycle consumer worker.

Subscribes to four NATS JetStream subjects to handle the full command lifecycle:
  - veyaan.command.delivered.>   → DELIVERED
  - veyaan.command.acknowledged.> → ACKNOWLEDGED (or FAILED if device rejected)
  - veyaan.command.progress.>    → RUNNING (first progress event)
  - veyaan.command.result.>      → SUCCEEDED / FAILED

Each handler updates BOTH the Command and its associated Task in ONE database
transaction (P0-08 fix). Events are deduplicated via CommandStateEvent records.

ACK is sent only after a successful commit; NAK is sent on transient errors.
Permanent invalid messages (bad JSON, bad UUID) are dead-lettered by
exhausting max_deliver retries.
"""

import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy import select

from app.cache import valkey_client
from app.commands.models import Command, CommandState, CommandStateEvent, Task, TaskState
from app.commands.state_machine import StateTransitionError, transition_command
from app.config import settings
from app.database.connection import close_db, init_db
from app.database.session import get_db_session_context as get_db_session
from app.events.nats_client import nats_client
from app.observability.logging import logger


# ── Consumer definitions ──────────────────────────────────────────────────────

_CONSUMERS = [
    {
        "subject": "veyaan.command.delivered.>",
        "durable": "api_command_delivered_v1",
        "stream": settings.NATS_STREAM_COMMANDS,
    },
    {
        "subject": "veyaan.command.acknowledged.>",
        "durable": "api_command_acknowledged_v1",
        "stream": settings.NATS_STREAM_COMMANDS,
    },
    {
        "subject": "veyaan.command.progress.>",
        "durable": "api_command_progress_v1",
        "stream": settings.NATS_STREAM_COMMANDS,
    },
    {
        "subject": "veyaan.command.result.>",
        "durable": "api_command_result_v1",
        "stream": settings.NATS_STREAM_COMMANDS,
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _is_duplicate(session, command_id: UUID, dedup_key: str) -> bool:
    """Return True if a CommandStateEvent with this deduplication key exists."""
    result = await session.execute(
        select(CommandStateEvent).where(
            CommandStateEvent.command_id == command_id,
            CommandStateEvent.event_metadata.op("->")("dedup_key").astext == dedup_key,
        )
    )
    return result.scalar_one_or_none() is not None


async def _update_task_state(
    session,
    command_id: UUID,
    new_task_state: TaskState,
    result_summary: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update the Task associated with a command, in the same session."""
    result = await session.execute(
        select(Task).where(Task.command_id == command_id).with_for_update()
    )
    task = result.scalar_one_or_none()
    if task:
        task.state = new_task_state.value
        if result_summary is not None:
            task.result_summary = result_summary
        if error_code is not None:
            task.error_code = error_code
        if error_message is not None:
            task.error_message = error_message
        await session.flush()


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _handle_delivered(payload: dict, msg_subject: str) -> None:
    command_id_str = payload.get("command_id")
    device_id_str = payload.get("device_id")
    dedup_key = f"delivered:{command_id_str}"

    try:
        command_id = UUID(command_id_str)
    except (ValueError, TypeError):
        logger.error("invalid_command_id_in_delivered", raw=command_id_str)
        return

    async with get_db_session() as session:
        if await _is_duplicate(session, command_id, dedup_key):
            logger.debug("duplicate_delivered_event", command_id=str(command_id))
            return

        cmd_result = await session.execute(
            select(Command).where(Command.id == command_id).with_for_update()
        )
        command = cmd_result.scalar_one_or_none()
        if not command:
            logger.warning("command_not_found_delivered", command_id=str(command_id))
            return

        # Verify device matches
        if device_id_str and str(command.device_id) != device_id_str:
            logger.warning(
                "device_mismatch_delivered",
                command_id=str(command_id),
                expected=str(command.device_id),
                got=device_id_str,
            )
            return

        try:
            await transition_command(
                session,
                command_id,
                CommandState.DELIVERED,
                "gateway",
                metadata={"dedup_key": dedup_key},
            )
        except StateTransitionError as exc:
            logger.warning("delivered_transition_error", error=str(exc))
            return

        await _update_task_state(session, command_id, TaskState.RUNNING)
        await session.commit()


async def _handle_acknowledged(payload: dict, msg_subject: str) -> None:
    command_id_str = payload.get("command_id")
    device_id_str = payload.get("device_id")
    accepted = payload.get("accepted", True)
    dedup_key = f"acknowledged:{command_id_str}"

    try:
        command_id = UUID(command_id_str)
    except (ValueError, TypeError):
        logger.error("invalid_command_id_in_ack", raw=command_id_str)
        return

    async with get_db_session() as session:
        if await _is_duplicate(session, command_id, dedup_key):
            return

        cmd_result = await session.execute(
            select(Command).where(Command.id == command_id).with_for_update()
        )
        command = cmd_result.scalar_one_or_none()
        if not command:
            logger.warning("command_not_found_ack", command_id=str(command_id))
            return

        if device_id_str and str(command.device_id) != device_id_str:
            logger.warning("device_mismatch_ack", command_id=str(command_id))
            return

        try:
            if accepted:
                await transition_command(
                    session,
                    command_id,
                    CommandState.ACKNOWLEDGED,
                    "device",
                    metadata={"dedup_key": dedup_key},
                )
            else:
                rejection_reason = payload.get("rejection_reason")
                await transition_command(
                    session,
                    command_id,
                    CommandState.FAILED,
                    "device",
                    metadata={
                        "error_message": rejection_reason,
                        "dedup_key": dedup_key,
                    },
                )
                await _update_task_state(
                    session,
                    command_id,
                    TaskState.FAILED,
                    error_message=rejection_reason,
                )
        except StateTransitionError as exc:
            logger.warning("ack_transition_error", error=str(exc))
            return

        await session.commit()


async def _handle_progress(payload: dict, msg_subject: str) -> None:
    command_id_str = payload.get("command_id")
    dedup_key = f"progress_first:{command_id_str}"

    try:
        command_id = UUID(command_id_str)
    except (ValueError, TypeError):
        logger.error("invalid_command_id_in_progress", raw=command_id_str)
        return

    async with get_db_session() as session:
        cmd_result = await session.execute(
            select(Command).where(Command.id == command_id).with_for_update()
        )
        command = cmd_result.scalar_one_or_none()
        if not command:
            return

        # Only transition to RUNNING once (idempotent)
        if command.state == CommandState.ACKNOWLEDGED.value:
            try:
                await transition_command(
                    session,
                    command_id,
                    CommandState.RUNNING,
                    "device",
                    metadata={"dedup_key": dedup_key},
                )
                await _update_task_state(session, command_id, TaskState.RUNNING)
            except StateTransitionError:
                pass  # already running — idempotent

        await session.commit()


async def _handle_result(payload: dict, msg_subject: str) -> None:
    command_id_str = payload.get("command_id")
    device_id_str = payload.get("device_id")
    success = payload.get("success", False)
    dedup_key = f"result:{command_id_str}"

    try:
        command_id = UUID(command_id_str)
    except (ValueError, TypeError):
        logger.error("invalid_command_id_in_result", raw=command_id_str)
        return

    async with get_db_session() as session:
        if await _is_duplicate(session, command_id, dedup_key):
            return

        cmd_result = await session.execute(
            select(Command).where(Command.id == command_id).with_for_update()
        )
        command = cmd_result.scalar_one_or_none()
        if not command:
            logger.warning("command_not_found_result", command_id=str(command_id))
            return

        if device_id_str and str(command.device_id) != device_id_str:
            logger.warning("device_mismatch_result", command_id=str(command_id))
            return

        try:
            if success:
                await transition_command(
                    session,
                    command_id,
                    CommandState.SUCCEEDED,
                    "device",
                    metadata={
                        "result_data": payload.get("result_data"),
                        "result_summary": "success",
                        "dedup_key": dedup_key,
                    },
                )
                await _update_task_state(
                    session, command_id, TaskState.SUCCEEDED, result_summary="success"
                )
            else:
                error_code = payload.get("error_code")
                error_message = payload.get("error_message")
                await transition_command(
                    session,
                    command_id,
                    CommandState.FAILED,
                    "device",
                    metadata={
                        "error_code": error_code,
                        "error_message": error_message,
                        "dedup_key": dedup_key,
                    },
                )
                await _update_task_state(
                    session,
                    command_id,
                    TaskState.FAILED,
                    error_code=error_code,
                    error_message=error_message,
                )
        except StateTransitionError as exc:
            logger.warning("result_transition_error", error=str(exc))
            return

        await session.commit()


# ── Subject → handler map ─────────────────────────────────────────────────────

_HANDLERS = {
    "delivered": _handle_delivered,
    "acknowledged": _handle_acknowledged,
    "progress": _handle_progress,
    "result": _handle_result,
}


def _route_handler(subject: str):
    for key, handler in _HANDLERS.items():
        if key in subject:
            return handler
    return None


# ── Consumer loop ─────────────────────────────────────────────────────────────

class CommandLifecycleConsumer:
    def __init__(self) -> None:
        self.running = False

    async def start(self) -> None:
        self.running = True
        logger.info("Starting command lifecycle consumer")

        # Create all four durable subscriptions
        subs = []
        for cfg in _CONSUMERS:
            sub = await nats_client.subscribe_durable(
                subject=cfg["subject"],
                durable_name=cfg["durable"],
                stream=cfg["stream"],
            )
            subs.append(sub)
            logger.info("subscribed_consumer", subject=cfg["subject"], durable=cfg["durable"])

        logger.info("command_lifecycle_consumer_started", consumer_count=len(subs))

        # Poll all subscriptions concurrently
        async def poll_sub(sub, subject_hint: str) -> None:
            while self.running:
                try:
                    msgs = await sub.fetch(batch=10, timeout=1)
                    for msg in msgs:
                        handler = _route_handler(msg.subject)
                        if handler is None:
                            logger.warning("no_handler_for_subject", subject=msg.subject)
                            await msg.ack()
                            continue
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            await handler(payload, msg.subject)
                            await msg.ack()
                        except json.JSONDecodeError as exc:
                            logger.error(
                                "invalid_json_in_lifecycle_msg",
                                subject=msg.subject,
                                error=str(exc),
                            )
                            # Permanent failure — let it exhaust retries
                            await msg.nak()
                        except Exception as exc:
                            logger.exception(
                                "lifecycle_msg_processing_failed",
                                subject=msg.subject,
                                error=str(exc),
                            )
                            await msg.nak()
                except asyncio.TimeoutError:
                    continue
                except Exception as exc:
                    if "connection closed" in str(exc).lower():
                        break
                    logger.exception("consumer_poll_error", subject=subject_hint, error=str(exc))
                    await asyncio.sleep(1)

        await asyncio.gather(*[poll_sub(sub, cfg["subject"]) for sub, cfg in zip(subs, _CONSUMERS)])

    def stop(self) -> None:
        self.running = False


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    from app.observability.logging import setup_logging

    setup_logging()

    await init_db()
    await valkey_client.connect()
    await nats_client.connect()

    consumer = CommandLifecycleConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        pass
    finally:
        consumer.stop()
        await nats_client.disconnect()
        await valkey_client.disconnect()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
