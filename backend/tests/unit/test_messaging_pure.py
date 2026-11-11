import uuid
from datetime import UTC, datetime

import pytest

from app.messaging import events as ev
from app.messaging.notify import notification_for
from app.messaging.relay import envelope
from app.messaging.topology import BINDINGS, Topology, next_hop

NOW = datetime(2030, 1, 1, 10, tzinfo=UTC)
TOPO = Topology(delays_ms=(5, 30, 120))


def test_next_hop_walks_the_retry_ladder_then_dead_letters():
    hops = [next_hop(TOPO, "notify", a, 5) for a in range(5)]
    assert hops == [
        "q.notify.retry.0",
        "q.notify.retry.1",
        "q.notify.retry.2",
        "q.notify.retry.2",
        "q.notify.dlq",
    ]
    assert next_hop(TOPO, "notify", 0, 1) == "q.notify.dlq"  # a single allowed delivery


def test_prefix_isolates_names():
    t = Topology(prefix="t1.")
    assert t.exchange_name == "t1.booking.events" and t.queue("promote") == "t1.q.promote"
    assert len(t.all_queues()) == len(BINDINGS) * (2 + len(t.delays_ms))


def booking_event(cls):
    p = ev.BookingPayload(
        booking_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        start_time=NOW,
        end_time=NOW,
        quantity=1,
        status="CONFIRMED",
    )
    return cls(aggregate_id=p.booking_id, occurred_at=NOW, payload=p)


@pytest.mark.parametrize(
    "cls",
    [
        ev.BookingConfirmed,
        ev.BookingWaitlisted,
        ev.BookingPromoted,
        ev.BookingCancelled,
        ev.BookingExpired,
    ],
)
def test_booking_events_notify_the_owner(cls):
    e = booking_event(cls)
    user_id, type_, payload = notification_for(e)
    assert user_id == e.payload.user_id and type_ == cls.__name__
    assert payload["message"] and payload["booking_id"] == str(e.payload.booking_id)


def test_capacity_and_resource_events_notify_nobody():
    released = ev.CapacityReleased(
        aggregate_id=uuid.uuid4(),
        occurred_at=NOW,
        payload=ev.CapacityReleasedPayload(
            resource_id=uuid.uuid4(),
            booking_id=uuid.uuid4(),
            start_time=NOW,
            end_time=NOW,
            quantity=1,
        ),
    )
    assert notification_for(released) is None


def test_envelope_round_trips_through_the_event_parser():
    e = booking_event(ev.BookingPromoted)
    row = {
        "event_id": e.event_id,
        "event_type": e.event_type,
        "schema_version": 1,
        "created_at": NOW,
        "aggregate_type": "booking",
        "aggregate_id": e.aggregate_id,
        "payload": e.payload.model_dump(mode="json"),
    }
    parsed = ev.parse_event(envelope(row))
    assert parsed.event_id == e.event_id and parsed.payload == e.payload
