import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.messaging import events as ev

NOW = datetime(2030, 1, 1, 10, tzinfo=UTC)
EVENTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "events"


def booking_payload(status: str) -> ev.BookingPayload:
    return ev.BookingPayload(
        booking_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        start_time=NOW,
        end_time=NOW,
        quantity=1,
        status=status,
    )


def make(name: str) -> ev._Envelope:
    cls = ev.EVENT_TYPES[name]
    base = dict(aggregate_id=uuid.uuid4(), occurred_at=NOW)
    if name == "CapacityReleased":
        payload = ev.CapacityReleasedPayload(
            resource_id=uuid.uuid4(),
            booking_id=uuid.uuid4(),
            start_time=NOW,
            end_time=NOW,
            quantity=2,
        )
    elif name == "ResourceUpdated":
        payload = ev.ResourceUpdatedPayload(resource_id=uuid.uuid4(), change="updated")
    else:
        payload = booking_payload("CONFIRMED")
    return cls(payload=payload, **base)


NAMES = list(ev.EVENT_TYPES)


def test_seven_events_defined():
    assert len(NAMES) == 7


@pytest.mark.parametrize("name", NAMES)
def test_round_trip(name):
    e = make(name)
    assert type(e).model_validate_json(e.model_dump_json()) == e


@pytest.mark.parametrize("name", NAMES)
def test_parse_event_dispatches_by_type(name):
    e = make(name)
    parsed = ev.parse_event(json.loads(e.model_dump_json()))
    assert type(parsed) is type(e)


@pytest.mark.parametrize("name", NAMES)
def test_every_event_has_routing_key(name):
    assert name in ev.ROUTING_KEYS


def test_unknown_event_type_rejected():
    with pytest.raises(ValueError):
        ev.parse_event({"event_type": "Nope"})


def test_extra_fields_rejected():
    data = json.loads(make("BookingConfirmed").model_dump_json())
    data["payload"]["surprise"] = 1
    with pytest.raises(ValidationError):
        ev.parse_event(data)


def test_unsupported_schema_version_rejected():
    data = json.loads(make("BookingConfirmed").model_dump_json())
    data["schema_version"] = 2
    with pytest.raises(ValidationError):
        ev.parse_event(data)


@pytest.mark.skipif(not EVENTS_DIR.exists(), reason="docs/events not present")
@pytest.mark.parametrize("name", NAMES)
def test_exported_schema_is_current(name):
    committed = (EVENTS_DIR / f"{name}.schema.json").read_text(encoding="utf-8")
    assert committed == ev.schema_json(ev.EVENT_TYPES[name]), (
        "schema changed: run python -m app.messaging.export_schemas and commit"
    )
