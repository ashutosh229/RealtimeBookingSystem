import random
from datetime import UTC, datetime, time, timedelta, timezone

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


def at(day, h, m=0):
    return datetime(2030, 1, day, h, m, tzinfo=UTC)


def test_hourly_and_half_hourly():
    assert slots.booking_slots(at(2, 9), at(2, 11), 60) == [at(2, 9), at(2, 10)]
    assert len(slots.booking_slots(at(2, 9), at(2, 10, 30), 30)) == 3


def test_returns_utc_even_for_other_offsets():
    ist = timezone(timedelta(hours=5, minutes=30))
    got = slots.booking_slots(at(2, 9).astimezone(ist), at(2, 10).astimezone(ist), 60)
    assert got == [at(2, 9)] and got[0].tzinfo == UTC


def test_release_slots_always_equal_acquire_slots():
    rng = random.Random(1)
    for _ in range(50):
        start_h, n = rng.randint(8, 18), rng.randint(1, 4)
        s, e = at(2, start_h), at(2, start_h + n)
        assert slots.validate_interval(RES, s, e, NOW) == slots.booking_slots(s, e, 60)
