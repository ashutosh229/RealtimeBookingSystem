"""Event contract (LLD section 26). Single source of truth; JSON schemas are exported from here."""

import json
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["REQUESTED", "CONFIRMED", "WAITLISTED", "CANCELLED", "COMPLETED", "EXPIRED"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BookingPayload(_Strict):
    booking_id: UUID
    user_id: UUID
    resource_id: UUID
    start_time: datetime
    end_time: datetime
    quantity: int = Field(ge=1)
    status: Status


class CapacityReleasedPayload(_Strict):
    resource_id: UUID
    booking_id: UUID
    start_time: datetime
    end_time: datetime
    quantity: int = Field(ge=1)


class ResourceUpdatedPayload(_Strict):
    resource_id: UUID
    change: Literal["created", "updated", "deactivated"]


class _Envelope(_Strict):
    event_id: UUID = Field(default_factory=uuid4)
    schema_version: Literal[1] = 1
    occurred_at: datetime
    aggregate_id: UUID


class BookingConfirmed(_Envelope):
    event_type: Literal["BookingConfirmed"] = "BookingConfirmed"
    aggregate_type: Literal["booking"] = "booking"
    payload: BookingPayload


class BookingWaitlisted(_Envelope):
    event_type: Literal["BookingWaitlisted"] = "BookingWaitlisted"
    aggregate_type: Literal["booking"] = "booking"
    payload: BookingPayload


class BookingPromoted(_Envelope):
    event_type: Literal["BookingPromoted"] = "BookingPromoted"
    aggregate_type: Literal["booking"] = "booking"
    payload: BookingPayload


class BookingCancelled(_Envelope):
    event_type: Literal["BookingCancelled"] = "BookingCancelled"
    aggregate_type: Literal["booking"] = "booking"
    payload: BookingPayload


class BookingExpired(_Envelope):
    event_type: Literal["BookingExpired"] = "BookingExpired"
    aggregate_type: Literal["booking"] = "booking"
    payload: BookingPayload


class CapacityReleased(_Envelope):
    event_type: Literal["CapacityReleased"] = "CapacityReleased"
    aggregate_type: Literal["booking"] = "booking"
    payload: CapacityReleasedPayload


class ResourceUpdated(_Envelope):
    event_type: Literal["ResourceUpdated"] = "ResourceUpdated"
    aggregate_type: Literal["resource"] = "resource"
    payload: ResourceUpdatedPayload


EVENT_TYPES: dict[str, type[_Envelope]] = {
    c.model_fields["event_type"].default: c
    for c in (
        BookingConfirmed,
        BookingWaitlisted,
        BookingPromoted,
        BookingCancelled,
        BookingExpired,
        CapacityReleased,
        ResourceUpdated,
    )
}

# RabbitMQ routing keys on the 'booking.events' topic exchange
ROUTING_KEYS = {
    "BookingConfirmed": "booking.confirmed",
    "BookingWaitlisted": "booking.waitlisted",
    "BookingPromoted": "booking.promoted",
    "BookingCancelled": "booking.cancelled",
    "BookingExpired": "booking.expired",
    "CapacityReleased": "capacity.released",
    "ResourceUpdated": "resource.updated",
}


def parse_event(data: dict) -> _Envelope:
    cls = EVENT_TYPES.get(data.get("event_type"))
    if cls is None:
        raise ValueError(f"unknown event_type: {data.get('event_type')!r}")
    return cls.model_validate(data)


def schema_json(cls: type[_Envelope]) -> str:
    return json.dumps(cls.model_json_schema(), indent=2, sort_keys=True) + "\n"
