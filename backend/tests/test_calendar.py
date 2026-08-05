"""Tests for build_calendar_data with mock shifts and scheduled shifts."""
from datetime import time
from app.services.calendar import build_calendar_data


class MockScheduledShift:
    """Lightweight stand-in for the ScheduledShift ORM model."""

    def __init__(self, day_of_week, start_time, end_time=None, department_id=None):
        self.day_of_week = day_of_week
        self.start_time = start_time
        self.end_time = end_time or time(17, 0)
        self.department_id = department_id


def _shift(in_time: str, out_time: str, minutes: int) -> dict:
    """Build a TimeStation-style shift dict."""
    return {
        "shift_id": "shift_1",
        "total_minutes": minutes,
        "in": {"time": in_time},
        "out": {"time": out_time},
    }


def test_on_time_shift_not_late():
    """A shift that clocks in before the late threshold should not be flagged late."""
    # 2026-08-03 is a Monday (weekday 0); scheduled start 09:00, clocks in 09:02
    shifts = [_shift("2026-08-03T09:02:00", "2026-08-03T17:05:00", 483)]
    scheduled = [MockScheduledShift(0, time(9, 0))]
    result = build_calendar_data(shifts, scheduled, "2026-08-03", "2026-08-03")

    assert len(result) == 1
    day = result[0]
    assert day["date"] == "2026-08-03"
    assert day["worked"] is True
    assert day["total_hours"] == round(483 / 60.0, 2)
    assert day["is_late"] is False
    assert day["late_minutes"] == 0
    assert len(day["shifts"]) == 1
    assert day["shifts"][0]["minutes"] == 483


def test_late_shift_flagged():
    """A shift that clocks in more than LATE_THRESHOLD_MINUTES late is flagged."""
    # 2026-08-03 is a Monday (weekday 0); scheduled 09:00, clocks in 09:12 (>5 min late)
    shifts = [_shift("2026-08-03T09:12:00", "2026-08-03T17:00:00", 468)]
    scheduled = [MockScheduledShift(0, time(9, 0))]
    result = build_calendar_data(shifts, scheduled, "2026-08-03", "2026-08-03")

    assert len(result) == 1
    day = result[0]
    assert day["worked"] is True
    assert day["is_late"] is True
    assert day["late_minutes"] == 12
    assert day["total_hours"] == round(468 / 60.0, 2)


def test_no_shifts_day_not_worked():
    """A day with no shifts should be marked as not worked."""
    shifts = []
    scheduled = [MockScheduledShift(0, time(9, 0))]
    result = build_calendar_data(shifts, scheduled, "2026-08-03", "2026-08-03")

    assert len(result) == 1
    day = result[0]
    assert day["date"] == "2026-08-03"
    assert day["worked"] is False
    assert day["total_hours"] == 0.0
    assert day["shifts"] == []
    assert day["is_late"] is False
    assert day["late_minutes"] == 0


def test_multi_day_range():
    """A multi-day range should return one entry per day."""
    shifts = [
        _shift("2026-08-03T09:00:00", "2026-08-03T17:00:00", 480),  # Mon on time
        _shift("2026-08-04T09:20:00", "2026-08-04T17:00:00", 460),  # Tue late
    ]
    scheduled = [
        MockScheduledShift(0, time(9, 0)),  # Monday
        MockScheduledShift(1, time(9, 0)),  # Tuesday
    ]
    result = build_calendar_data(shifts, scheduled, "2026-08-03", "2026-08-05")

    assert len(result) == 3
    assert result[0]["date"] == "2026-08-03"
    assert result[0]["worked"] is True
    assert result[0]["is_late"] is False
    assert result[1]["date"] == "2026-08-04"
    assert result[1]["worked"] is True
    assert result[1]["is_late"] is True
    assert result[1]["late_minutes"] == 20
    assert result[2]["date"] == "2026-08-05"
    assert result[2]["worked"] is False


def test_no_scheduled_shift_no_late_flag():
    """If there's no scheduled shift for that weekday, is_late should be False."""
    shifts = [_shift("2026-08-03T10:00:00", "2026-08-03T17:00:00", 420)]
    scheduled = []  # no schedule defined
    result = build_calendar_data(shifts, scheduled, "2026-08-03", "2026-08-03")

    assert result[0]["is_late"] is False
    assert result[0]["late_minutes"] == 0
    assert result[0]["worked"] is True


def test_multiple_shifts_same_day():
    """Multiple shifts on the same day are grouped and totalled."""
    shifts = [
        _shift("2026-08-03T09:00:00", "2026-08-03T12:00:00", 180),
        _shift("2026-08-03T13:00:00", "2026-08-03T17:00:00", 240),
    ]
    scheduled = [MockScheduledShift(0, time(9, 0))]
    result = build_calendar_data(shifts, scheduled, "2026-08-03", "2026-08-03")

    day = result[0]
    assert day["worked"] is True
    assert day["total_hours"] == round(420 / 60.0, 2)
    assert len(day["shifts"]) == 2
    assert day["is_late"] is False
