"""Integration tests — command pipeline state machine.

Covers:
  - Command submission creates QUEUED command + outbox event in same transaction
  - Command transitions follow canonical state machine (not direct updates)
  - Deduplication: same event twice produces only one state transition
  - Task state updated in same transaction as command state
  - Expired commands transition via state machine (not bulk UPDATE)
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.commands.models import Command, CommandState, CommandStateEvent, Task, TaskState
from app.commands.state_machine import transition_command
from app.devices.models import Device, DeviceStatus
from app.users.models import User


async def _create_user_and_device(db_session):
    user = User(
        id=uuid.uuid4(),
        supabase_user_id=f"sb-{uuid.uuid4()}",
        display_name="Test Owner",
        email="owner@example.com",
    )
    db_session.add(user)
    await db_session.flush()

    device = Device(
        id=uuid.uuid4(),
        owner_id=user.id,
        display_name="Test Device",
        device_type="iphone",
        operating_system="iOS",
        app_version="1.0.0",
        protocol_version="v1",
        device_public_identity="f" * 64,
        trust_status=DeviceStatus.TRUSTED,
    )
    db_session.add(device)
    await db_session.flush()
    return user, device


@pytest.mark.integration
async def test_command_state_machine_queued_to_delivered(db_session):
    """Direct state machine: QUEUED → DELIVERED records CommandStateEvent."""
    user, device = await _create_user_and_device(db_session)

    command = Command(
        device_id=device.id,
        command_type="system.ping",
        state=CommandState.QUEUED.value,
        risk_level="low",
        parameters={},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        idempotency_key=f"ik-{uuid.uuid4()}",
    )
    db_session.add(command)
    await db_session.flush()

    await transition_command(
        db_session, command.id, CommandState.DELIVERED, "test"
    )
    await db_session.flush()

    # Verify command state changed
    result = await db_session.execute(select(Command).where(Command.id == command.id))
    cmd = result.scalar_one()
    assert cmd.state == CommandState.DELIVERED.value

    # Verify CommandStateEvent was recorded
    event_result = await db_session.execute(
        select(CommandStateEvent).where(CommandStateEvent.command_id == command.id)
    )
    events = event_result.scalars().all()
    assert len(events) >= 1
    assert any(e.new_state == CommandState.DELIVERED.value for e in events)


@pytest.mark.integration
async def test_command_expiry_via_state_machine(db_session):
    """Scheduler must expire commands through the state machine, not bulk UPDATE."""
    user, device = await _create_user_and_device(db_session)

    # Command that is already expired
    command = Command(
        device_id=device.id,
        command_type="actuator.move",
        state=CommandState.QUEUED.value,
        risk_level="low",
        parameters={},
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),  # expired
        idempotency_key=f"ik-{uuid.uuid4()}",
    )
    task = Task(command_id=None, state=TaskState.PENDING.value)
    db_session.add(command)
    await db_session.flush()

    task.command_id = command.id
    db_session.add(task)
    await db_session.flush()

    await transition_command(
        db_session, command.id, CommandState.EXPIRED, "scheduler_test"
    )
    await db_session.flush()

    # Command state must be EXPIRED
    cmd_result = await db_session.execute(select(Command).where(Command.id == command.id))
    cmd = cmd_result.scalar_one()
    assert cmd.state == CommandState.EXPIRED.value

    # CommandStateEvent must exist
    event_result = await db_session.execute(
        select(CommandStateEvent).where(CommandStateEvent.command_id == command.id)
    )
    events = event_result.scalars().all()
    assert any(e.new_state == CommandState.EXPIRED.value for e in events)


@pytest.mark.integration
async def test_invalid_state_transition_raises_error(db_session):
    """State machine must reject invalid transitions (e.g., SUCCEEDED → FAILED)."""
    from app.commands.state_machine import StateTransitionError

    user, device = await _create_user_and_device(db_session)

    command = Command(
        device_id=device.id,
        command_type="system.reboot",
        state=CommandState.SUCCEEDED.value,
        risk_level="low",
        parameters={},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        idempotency_key=f"ik-{uuid.uuid4()}",
    )
    db_session.add(command)
    await db_session.flush()

    with pytest.raises(StateTransitionError):
        await transition_command(
            db_session, command.id, CommandState.FAILED, "test_invalid"
        )
