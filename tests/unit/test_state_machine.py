"""Unit tests for the command state machine.

Tests every documented allowed and denied transition.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.commands.models import CommandState
from app.commands.state_machine import (
    TERMINAL_STATES,
    StateTransitionError,
    transition_command,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_command(state: CommandState):
    """Return a mock Command object in a given state."""
    cmd = MagicMock()
    cmd.id = uuid4()
    cmd.state = state.value
    cmd.updated_at = None
    cmd.delivered_at = None
    cmd.acknowledged_at = None
    cmd.started_at = None
    cmd.finished_at = None
    cmd.result_data = None
    cmd.result_summary = None
    cmd.error_code = None
    cmd.error_message = None
    return cmd


def _make_session(command):
    """Return a mock async session that yields the given command."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = command
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------


class TestAllowedTransitions:
    @pytest.mark.asyncio
    async def test_received_to_validated(self):
        cmd = _make_command(CommandState.RECEIVED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.VALIDATED, "api")
        assert result is not None

    @pytest.mark.asyncio
    async def test_validated_to_queued(self):
        cmd = _make_command(CommandState.VALIDATED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.QUEUED, "api")
        assert result is not None

    @pytest.mark.asyncio
    async def test_validated_to_awaiting_approval(self):
        cmd = _make_command(CommandState.VALIDATED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.AWAITING_APPROVAL, "api")
        assert result is not None

    @pytest.mark.asyncio
    async def test_awaiting_approval_to_approved(self):
        cmd = _make_command(CommandState.AWAITING_APPROVAL)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.APPROVED, "approval")
        assert result is not None

    @pytest.mark.asyncio
    async def test_awaiting_approval_to_rejected(self):
        cmd = _make_command(CommandState.AWAITING_APPROVAL)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.REJECTED, "approval")
        assert result is not None

    @pytest.mark.asyncio
    async def test_approved_to_queued(self):
        cmd = _make_command(CommandState.APPROVED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.QUEUED, "system")
        assert result is not None

    @pytest.mark.asyncio
    async def test_queued_to_delivered(self):
        cmd = _make_command(CommandState.QUEUED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.DELIVERED, "gateway")
        assert result is not None

    @pytest.mark.asyncio
    async def test_delivered_to_acknowledged(self):
        cmd = _make_command(CommandState.DELIVERED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.ACKNOWLEDGED, "gateway")
        assert result is not None

    @pytest.mark.asyncio
    async def test_acknowledged_to_running(self):
        cmd = _make_command(CommandState.ACKNOWLEDGED)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.RUNNING, "gateway")
        assert result is not None

    @pytest.mark.asyncio
    async def test_running_to_succeeded(self):
        cmd = _make_command(CommandState.RUNNING)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.SUCCEEDED, "gateway")
        assert result is not None

    @pytest.mark.asyncio
    async def test_running_to_failed(self):
        cmd = _make_command(CommandState.RUNNING)
        session = _make_session(cmd)
        result = await transition_command(session, cmd.id, CommandState.FAILED, "gateway")
        assert result is not None


# ---------------------------------------------------------------------------
# Denied / invalid transitions
# ---------------------------------------------------------------------------


class TestDeniedTransitions:
    @pytest.mark.asyncio
    async def test_rejected_cannot_move_to_queued(self):
        cmd = _make_command(CommandState.REJECTED)
        session = _make_session(cmd)
        with pytest.raises(StateTransitionError):
            await transition_command(session, cmd.id, CommandState.QUEUED, "test")

    @pytest.mark.asyncio
    async def test_succeeded_cannot_move_to_running(self):
        cmd = _make_command(CommandState.SUCCEEDED)
        session = _make_session(cmd)
        with pytest.raises(StateTransitionError):
            await transition_command(session, cmd.id, CommandState.RUNNING, "test")

    @pytest.mark.asyncio
    async def test_expired_cannot_move_to_delivered(self):
        cmd = _make_command(CommandState.EXPIRED)
        session = _make_session(cmd)
        with pytest.raises(StateTransitionError):
            await transition_command(session, cmd.id, CommandState.DELIVERED, "test")

    @pytest.mark.asyncio
    async def test_failed_cannot_move_to_running(self):
        cmd = _make_command(CommandState.FAILED)
        session = _make_session(cmd)
        with pytest.raises(StateTransitionError):
            await transition_command(session, cmd.id, CommandState.RUNNING, "test")

    @pytest.mark.asyncio
    async def test_received_cannot_skip_to_queued(self):
        cmd = _make_command(CommandState.RECEIVED)
        session = _make_session(cmd)
        with pytest.raises(StateTransitionError):
            await transition_command(session, cmd.id, CommandState.QUEUED, "test")

    @pytest.mark.asyncio
    async def test_cancelled_cannot_move_to_delivered(self):
        cmd = _make_command(CommandState.CANCELLED)
        session = _make_session(cmd)
        with pytest.raises(StateTransitionError):
            await transition_command(session, cmd.id, CommandState.DELIVERED, "test")


# ---------------------------------------------------------------------------
# Terminal state coverage
# ---------------------------------------------------------------------------


class TestTerminalStates:
    def test_terminal_states_are_correct(self):
        assert CommandState.SUCCEEDED in TERMINAL_STATES
        assert CommandState.FAILED in TERMINAL_STATES
        assert CommandState.TIMED_OUT in TERMINAL_STATES
        assert CommandState.CANCELLED in TERMINAL_STATES
        assert CommandState.EXPIRED in TERMINAL_STATES
        assert CommandState.REJECTED in TERMINAL_STATES
        assert CommandState.BLOCKED_BY_EMERGENCY_STOP in TERMINAL_STATES

    def test_non_terminal_states_not_in_terminal(self):
        assert CommandState.RECEIVED not in TERMINAL_STATES
        assert CommandState.QUEUED not in TERMINAL_STATES
        assert CommandState.RUNNING not in TERMINAL_STATES
        assert CommandState.DELIVERED not in TERMINAL_STATES

    @pytest.mark.asyncio
    async def test_command_not_found_returns_none(self):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        result = await transition_command(session, uuid4(), CommandState.QUEUED, "test")
        assert result is None
