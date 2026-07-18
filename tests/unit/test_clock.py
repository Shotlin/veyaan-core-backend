"""
Unit tests for the FakeClock and clock abstraction.
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.clock import FakeClock, SystemClock


class TestFakeClock:

    def test_returns_fixed_time(self):
        t = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
        clock = FakeClock(t)
        assert clock.now() == t

    def test_utcnow_equals_now(self):
        t = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
        clock = FakeClock(t)
        assert clock.utcnow() == clock.now()

    def test_advance_seconds(self):
        t = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
        clock = FakeClock(t)
        clock.advance(seconds=90)
        assert clock.now() == t + timedelta(seconds=90)

    def test_advance_minutes(self):
        t = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
        clock = FakeClock(t)
        clock.advance(minutes=31)
        assert clock.now() == t + timedelta(minutes=31)

    def test_advance_days(self):
        t = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
        clock = FakeClock(t)
        clock.advance(days=5)
        assert clock.now() == t + timedelta(days=5)

    def test_set_time(self):
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 12, 31, tzinfo=timezone.utc)
        clock = FakeClock(t1)
        clock.set(t2)
        assert clock.now() == t2

    def test_default_time_is_timezone_aware(self):
        clock = FakeClock()
        assert clock.now().tzinfo is not None

    def test_expiry_check_with_fake_clock(self):
        """Demonstrates using FakeClock for expiry logic."""
        expires_at = datetime(2026, 7, 18, 12, 30, tzinfo=timezone.utc)
        clock = FakeClock(datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc))

        assert clock.now() < expires_at  # Not yet expired

        clock.advance(minutes=31)
        assert clock.now() > expires_at  # Now expired


class TestSystemClock:

    def test_returns_utc_aware_datetime(self):
        clock = SystemClock()
        now = clock.now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc or now.utcoffset() is not None

    def test_now_and_utcnow_are_close(self):
        clock = SystemClock()
        t1 = clock.now()
        t2 = clock.utcnow()
        # Should be within 1 second of each other
        diff = abs((t2 - t1).total_seconds())
        assert diff < 1.0
