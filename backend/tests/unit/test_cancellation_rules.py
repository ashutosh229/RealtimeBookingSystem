from datetime import UTC, datetime, timedelta

import pytest

from app.booking.service import check_cancellable
from app.platform.errors import ApiError

NOW = datetime(2030, 1, 1, 9, 30, tzinfo=UTC)


def booking(
    status="CONFIRMED",
    starts_in=timedelta(hours=24),
    length=timedelta(hours=1),
    notice=0,
):
    start = NOW + starts_in
    return {
        "status": status,
        "start_time": start,
        "end_time": start + length,
        "min_cancel_notice_minutes": notice,
    }


def closed(b, role):
    with pytest.raises(ApiError) as ei:
        check_cancellable(b, role, NOW)
    assert ei.value.status == 409 and ei.value.code == "CANCELLATION_WINDOW_CLOSED"


def test_student_before_start_ok():
    check_cancellable(booking(), "student", NOW)


def test_student_at_or_after_start_refused():
    closed(booking(starts_in=timedelta(0)), "student")
    closed(booking(starts_in=timedelta(minutes=-10)), "student")


def test_student_notice_window():
    closed(booking(starts_in=timedelta(minutes=30), notice=60), "student")
    check_cancellable(booking(starts_in=timedelta(minutes=90), notice=60), "student", NOW)


def test_waitlisted_can_always_be_withdrawn():
    check_cancellable(
        booking("WAITLISTED", starts_in=timedelta(hours=-3), notice=999), "student", NOW
    )


def test_admin_ignores_notice_and_start_but_not_end():
    check_cancellable(booking(starts_in=timedelta(minutes=10), notice=999), "admin", NOW)
    check_cancellable(booking(starts_in=timedelta(minutes=-30)), "admin", NOW)  # in progress
    closed(booking(starts_in=timedelta(hours=-3)), "admin")  # already ended
