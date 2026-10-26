"""Slot generation and interval validation (LLD section 19). No database access."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.platform.errors import ApiError


def _bad(msg: str, code: str = "INVALID_INTERVAL") -> ApiError:
    return ApiError(422, code, msg)


def zone_of(res: Mapping) -> ZoneInfo:
    return ZoneInfo(res["timezone"])


def day_slots(res: Mapping, day: date) -> list[datetime]:
    """UTC start instants of every slot on a resource-local day, stepping in wall-clock minutes."""
    z, step = zone_of(res), res["slot_minutes"]
    cur = res["open_time"].hour * 60 + res["open_time"].minute
    close = res["close_time"].hour * 60 + res["close_time"].minute
    out: list[datetime] = []
    while cur + step <= close:
        local = datetime.combine(day, time(cur // 60, cur % 60), tzinfo=z)
        out.append(local.astimezone(UTC))
        cur += step
    return out


def _check_aware(*values: datetime) -> None:
    if any(v.tzinfo is None for v in values):
        raise _bad("timestamps must include a timezone offset")


def _check_aligned(res: Mapping, value: datetime) -> None:
    loc = value.astimezone(zone_of(res))
    if loc.second or loc.microsecond or (loc.hour * 60 + loc.minute) % res["slot_minutes"]:
        raise _bad(f"times must align to {res['slot_minutes']}-minute slot boundaries")


def validate_interval(
    res: Mapping, start: datetime, end: datetime, now: datetime
) -> list[datetime]:
    """Return the UTC slot starts covered by [start, end), or raise a 422 ApiError."""
    _check_aware(start, end)
    if end <= start:
        raise _bad("end_time must be after start_time")
    _check_aligned(res, start)
    step = timedelta(minutes=res["slot_minutes"])
    if (end - start) % step:
        raise _bad(f"duration must be a multiple of {res['slot_minutes']} minutes")
    n = (end - start) // step
    if n > res["max_slots_per_booking"]:
        raise _bad(f"a booking may span at most {res['max_slots_per_booking']} slots")
    if start <= now:
        raise _bad("start_time must be in the future")
    if start > now + timedelta(days=res["booking_horizon_days"]):
        raise _bad(f"bookings open {res['booking_horizon_days']} days ahead", "OUT_OF_HORIZON")
    slots = booking_slots(start, end, res["slot_minutes"])
    allowed = set(day_slots(res, start.astimezone(zone_of(res)).date()))
    if not set(slots) <= allowed:
        raise _bad(
            "outside operating hours (a booking must fit within one day)",
            "OUT_OF_HOURS",
        )
    return slots


def range_slots(res: Mapping, frm: datetime, to: datetime) -> list[datetime]:
    _check_aware(frm, to)
    if to <= frm:
        raise _bad("'to' must be after 'from'")
    if to - frm > timedelta(days=7):
        raise _bad("range may not exceed 7 days")
    _check_aligned(res, frm)
    z = zone_of(res)
    day, last = frm.astimezone(z).date(), to.astimezone(z).date()
    out: list[datetime] = []
    while day <= last:
        out += [s for s in day_slots(res, day) if frm <= s < to]
        day += timedelta(days=1)
    return out


def booking_slots(start: datetime, end: datetime, slot_minutes: int) -> list[datetime]:
    """UTC slot starts covered by a validated booking. Single source of truth for acquire AND release."""
    step = timedelta(minutes=slot_minutes)
    return [(start + i * step).astimezone(UTC) for i in range((end - start) // step)]
