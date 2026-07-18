"""
Clock abstraction for testable time-dependent logic.

Instead of calling `datetime.now(timezone.utc)` directly throughout the codebase,
inject `Clock` to make time mockable in unit tests — no monkey-patching needed.

Usage:
    from app.utils.clock import SystemClock, Clock

    class MyService:
        def __init__(self, clock: Clock = None):
            self.clock = clock or SystemClock()

        def is_expired(self, expires_at: datetime) -> bool:
            return self.clock.now() > expires_at

Test:
    from app.utils.clock import FakeClock
    from datetime import datetime, timezone

    fixed = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(fixed)
    assert clock.now() == fixed
    clock.advance(seconds=90)
    assert clock.now() > fixed
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    """Protocol for clock injection — makes time-dependent code unit testable."""

    def now(self) -> datetime:
        """Return the current UTC datetime (timezone-aware)."""
        ...

    def utcnow(self) -> datetime:
        """Alias for now() — returns UTC datetime."""
        ...


class SystemClock:
    """Production clock — delegates to datetime.now(timezone.utc)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """
    Test clock with a fixed time that can be advanced manually.

    Example:
        clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert clock.now().year == 2026
        clock.advance(days=1)
        assert clock.now().day == 2
    """

    def __init__(self, fixed_time: datetime | None = None):
        self._time = fixed_time or datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._time

    def utcnow(self) -> datetime:
        return self._time

    def set(self, dt: datetime) -> None:
        """Set the clock to a specific time."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        self._time = dt

    def advance(
        self,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        days: int = 0,
    ) -> None:
        """Advance the clock by the given duration."""
        self._time += timedelta(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            days=days,
        )


# Module-level singleton — use for production code
system_clock = SystemClock()
