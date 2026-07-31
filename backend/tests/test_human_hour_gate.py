"""Tests for the human-sending-hours gate in messaging_throttle.py (Capa 14
anti-baneo) — Mon-Sat 8am-9pm, Sunday blocked outright. Exercises the pure
_is_human_hour_at / _next_human_hour_after helpers with hand-built datetimes
instead of mocking the wall clock (no freezegun in this repo's deps)."""
from datetime import datetime, timezone, timedelta

import pytest

from app.services.messaging_throttle import (
    _is_human_hour_at,
    _next_human_hour_after,
    is_human_hour,
    next_human_hour_utc,
)

_MX = timezone(timedelta(hours=-6))


def _mx(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=_MX)


class TestIsHumanHourAt:
    def test_monday_mid_morning_is_human_hour(self):
        assert _is_human_hour_at(_mx(2026, 8, 3, 10)) is True  # Monday

    def test_saturday_afternoon_is_human_hour(self):
        assert _is_human_hour_at(_mx(2026, 8, 1, 15)) is True  # Saturday

    def test_before_8am_is_blocked(self):
        assert _is_human_hour_at(_mx(2026, 8, 3, 7, 59)) is False

    def test_exactly_8am_is_allowed(self):
        assert _is_human_hour_at(_mx(2026, 8, 3, 8, 0)) is True

    def test_exactly_9pm_is_blocked(self):
        assert _is_human_hour_at(_mx(2026, 8, 3, 21, 0)) is False

    def test_just_before_9pm_is_allowed(self):
        assert _is_human_hour_at(_mx(2026, 8, 3, 20, 59)) is True

    def test_sunday_is_blocked_regardless_of_hour(self):
        sunday = _mx(2026, 8, 2, 14)  # Sunday, 2pm — well within the hour window
        assert sunday.weekday() == 6
        assert _is_human_hour_at(sunday) is False


class TestNextHumanHourAfter:
    def test_early_morning_same_day_rolls_to_8am_same_day(self):
        result = _next_human_hour_after(_mx(2026, 8, 3, 3))  # Monday 3am
        assert result == _mx(2026, 8, 3, 8)

    def test_late_night_rolls_to_next_day_8am(self):
        result = _next_human_hour_after(_mx(2026, 8, 3, 22))  # Monday 10pm
        assert result == _mx(2026, 8, 4, 8)  # Tuesday 8am

    def test_saturday_night_skips_sunday_to_monday(self):
        result = _next_human_hour_after(_mx(2026, 8, 1, 22))  # Saturday 10pm
        assert result == _mx(2026, 8, 3, 8)  # Monday 8am, not Sunday

    def test_sunday_morning_rolls_to_monday_not_later_sunday(self):
        result = _next_human_hour_after(_mx(2026, 8, 2, 3))  # Sunday 3am
        assert result == _mx(2026, 8, 3, 8)  # Monday 8am

    def test_sunday_afternoon_rolls_to_monday(self):
        result = _next_human_hour_after(_mx(2026, 8, 2, 15))  # Sunday 3pm
        assert result == _mx(2026, 8, 3, 8)

    def test_result_is_always_within_human_hour(self):
        """Whatever comes out must itself satisfy _is_human_hour_at — the
        one invariant that actually matters end-to-end."""
        for start in [
            _mx(2026, 8, 1, 22),  # Saturday night
            _mx(2026, 8, 2, 3),   # Sunday early morning
            _mx(2026, 8, 2, 20),  # Sunday evening
            _mx(2026, 8, 3, 6),   # Monday pre-dawn
        ]:
            assert _is_human_hour_at(_next_human_hour_after(start)) is True


class TestPublicWrappers:
    def test_is_human_hour_returns_a_bool(self):
        assert isinstance(is_human_hour(), bool)

    def test_next_human_hour_utc_is_in_the_future_and_utc(self):
        now = datetime.now(timezone.utc)
        result = next_human_hour_utc()
        assert result.tzinfo is not None
        assert result >= now
