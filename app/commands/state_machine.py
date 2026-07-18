from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.models import Command, CommandState, CommandStateEvent


class StateTransitionError(Exception):
    def __init__(self, command_id: UUID, from_state: CommandState, to_state: CommandState):
        self.command_id = command_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Cannot transition {from_state.value} -> {to_state.value}")


ALLOWED_TRANSITIONS: dict[CommandState, set[CommandState]] = {
    CommandState.RECEIVED: {CommandState.VALIDATED},
    CommandState.VALIDATED: {CommandState.AWAITING_APPROVAL, CommandState.QUEUED, CommandState.REJECTED, CommandState.BLOCKED_BY_EMERGENCY_STOP},
    CommandState.AWAITING_APPROVAL: {CommandState.APPROVED, CommandState.REJECTED, CommandState.EXPIRED, CommandState.CANCELLED},
    CommandState.APPROVED: {CommandState.QUEUED, CommandState.BLOCKED_BY_EMERGENCY_STOP, CommandState.EXPIRED, CommandState.CANCELLED},
    CommandState.QUEUED: {CommandState.DELIVERED, CommandState.BLOCKED_BY_EMERGENCY_STOP, CommandState.EXPIRED, CommandState.CANCELLED, CommandState.FAILED},
    CommandState.DELIVERED: {CommandState.ACKNOWLEDGED, CommandState.TIMED_OUT, CommandState.CANCELLED, CommandState.FAILED},
    CommandState.ACKNOWLEDGED: {CommandState.RUNNING, CommandState.FAILED, CommandState.CANCELLED},
    CommandState.RUNNING: {CommandState.SUCCEEDED, CommandState.FAILED, CommandState.TIMED_OUT, CommandState.CANCELLED},
}


TERMINAL_STATES = {
    CommandState.SUCCEEDED,
    CommandState.FAILED,
    CommandState.TIMED_OUT,
    CommandState.CANCELLED,
    CommandState.EXPIRED,
    CommandState.REJECTED,
    CommandState.BLOCKED_BY_EMERGENCY_STOP,
}


async def transition_command(
    session: AsyncSession,
    command_id: UUID,
    new_state: CommandState,
    event_source: str = "system",
    metadata: dict | None = None,
) -> Command | None:
    result = await session.execute(
        select(Command)
        .where(Command.id == command_id)
        .with_for_update()
    )
    command = result.scalar_one_or_none()
    if not command:
        return None

    current_state = CommandState(command.state)
    if current_state in TERMINAL_STATES and current_state != new_state:
        raise StateTransitionError(command_id, current_state, new_state)

    if new_state not in ALLOWED_TRANSITIONS.get(current_state, set()):
        if current_state != new_state:
            raise StateTransitionError(command_id, current_state, new_state)

    previous_state = command.state
    command.state = new_state.value
    command.updated_at = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    if new_state == CommandState.DELIVERED:
        command.delivered_at = now
    elif new_state == CommandState.ACKNOWLEDGED:
        command.acknowledged_at = now
    elif new_state == CommandState.RUNNING:
        command.started_at = now
    elif new_state in (CommandState.SUCCEEDED,):
        command.finished_at = now
        if metadata and "result_data" in metadata:
            command.result_data = metadata["result_data"]
        if metadata and "result_summary" in metadata:
            command.result_summary = metadata["result_summary"]
    elif new_state in (CommandState.FAILED,):
        command.finished_at = now
        if metadata:
            command.error_code = metadata.get("error_code")
            command.error_message = metadata.get("error_message")
    elif new_state in (CommandState.TIMED_OUT, CommandState.CANCELLED, CommandState.EXPIRED):
        command.finished_at = now

    await session.flush()

    event = CommandStateEvent(
        command_id=command.id,
        previous_state=previous_state,
        new_state=new_state.value,
        event_source=event_source,
        event_metadata=metadata,
    )
    session.add(event)
    await session.flush()

    return command
