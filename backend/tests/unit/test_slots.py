from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.platform.errors import ApiError
from app.resources import slots

RES = dict(
    timezone="UTC",
    slot_minutes=60,
    open_time=time(8),
    close_time=time(22),
    max_slots_per_booking=4,
    booking_horizon_days=14,
)
NOW = datetime(2030, 1, 1, 9, 30, tzinfo=UTC)


def at(day: int, h: int, m: int = 0) -> datetime:
    return datetime(2030, 1, day, h, m, tzinfo=UTC)


def code(start, end, res=RES) -> str:
    with pytest.raises(ApiError) as ei:
        slots.validate_interval(res, start, end, NOW)
    assert ei.value.status == 422
    return ei.value.code


def test_valid_interval_returns_slot_starts():
    assert slots.validate_interval(RES, at(2, 9), at(2, 11), NOW) == [
        at(2, 9),
        at(2, 10),
    ]


def test_adjacent_bookings_share_no_slot():
    a = slots.validate_interval(RES, at(2, 9), at(2, 10), NOW)
    b = slots.validate_interval(RES, at(2, 10), at(2, 11), NOW)
    assert not set(a) & set(b)  # [start, end) semantics


def test_misaligned_start():
    assert code(at(2, 9, 30), at(2, 11, 30)) == "INVALID_INTERVAL"


def test_duration_not_multiple_of_slot():
    assert code(at(2, 9), at(2, 10, 30)) == "INVALID_INTERVAL"


def test_end_not_after_start():
    assert code(at(2, 10), at(2, 10)) == "INVALID_INTERVAL"
    assert code(at(2, 11), at(2, 10)) == "INVALID_INTERVAL"


def test_naive_datetime_rejected():
    assert code(datetime(2030, 1, 2, 9), datetime(2030, 1, 2, 10)) == "INVALID_INTERVAL"


def test_too_many_slots():
    assert code(at(2, 9), at(2, 14)) == "INVALID_INTERVAL"  # 5 slots, max 4


def test_start_in_the_past():
    assert code(at(1, 9), at(1, 10)) == "INVALID_INTERVAL"


def test_outside_operating_hours():
    assert code(at(2, 7), at(2, 8)) == "OUT_OF_HOURS"
    assert code(at(2, 21), at(2, 23)) == "OUT_OF_HOURS"


def test_beyond_horizon():
    assert code(at(20, 9), at(20, 10)) == "OUT_OF_HORIZON"


def test_offset_timestamps_are_normalised():
    ist = dict(RES, timezone="Asia/Kolkata")
    start = datetime(2030, 1, 2, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert slots.validate_interval(ist, start, start + timedelta(hours=1), NOW) == [at(2, 3, 30)]


def test_day_slot_counts():
    assert len(slots.day_slots(RES, at(2, 0).date())) == 14
    assert len(slots.day_slots(dict(RES, slot_minutes=30), at(2, 0).date())) == 28


def test_day_slots_follow_dst():
    ny = dict(RES, timezone="America/New_York")
    before = slots.day_slots(ny, datetime(2030, 3, 9).date())  # EST, UTC-5
    after = slots.day_slots(
        ny, datetime(2030, 3, 10).date()
    )  # DST starts at 02:00 this day, EDT UTC-4
    assert (before[0].hour, after[0].hour) == (13, 12)
    assert len(before) == len(after) == 14


def test_range_slots_spans_days_and_clips_to_hours():
    got = slots.range_slots(RES, at(2, 21), at(3, 10))
    assert got == [at(2, 21), at(3, 8), at(3, 9)]


def test_range_slots_limits():
    with pytest.raises(ApiError):
        slots.range_slots(RES, at(2, 9), at(12, 9))
    with pytest.raises(ApiError):
        slots.range_slots(RES, at(2, 10), at(2, 9))
