from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from app.booking.schemas import BookingCreate
from app.booking.service import request_hash

RID = uuid4()
UTC_START = datetime(2030, 1, 2, 9, tzinfo=UTC)


def cmd(**over) -> BookingCreate:
    base = dict(resource_id=RID, start_time=UTC_START, end_time=UTC_START + timedelta(hours=1))
    return BookingCreate(**{**base, **over})


def test_same_instant_in_other_offsets_hashes_equal():
    ist = timezone(timedelta(hours=5, minutes=30))
    other = cmd(
        start_time=UTC_START.astimezone(ist),
        end_time=(UTC_START + timedelta(hours=1)).astimezone(ist),
    )
    assert request_hash(cmd()) == request_hash(other)


def test_any_field_change_changes_the_hash():
    base = request_hash(cmd())
    assert request_hash(cmd(quantity=2)) != base
    assert request_hash(cmd(waitlist_if_full=True)) != base
    assert request_hash(cmd(end_time=UTC_START + timedelta(hours=2))) != base
    assert request_hash(cmd(resource_id=uuid4())) != base
