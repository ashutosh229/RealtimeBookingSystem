from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

ResourceType = Literal["SEAT", "ROOM", "COMPUTE_POOL"]
PolicyName = Literal["FIFO", "FAIR_SHARE", "FAIR_SHARE_Q"]
SlotMinutes = Literal[15, 30, 60, 120]


class ResourceOut(BaseModel):
    resource_id: UUID
    type: ResourceType
    name: str
    capacity: int
    slot_minutes: int
    open_time: time
    close_time: time
    timezone: str
    max_slots_per_booking: int
    max_quantity_per_booking: int
    policy_name: PolicyName
    lat: float | None = None
    lon: float | None = None
    distance_m: float | None = None
    eligible_groups: list[str] = []
    active: bool

    @field_serializer("open_time", "close_time")
    def _hhmm(self, v: time) -> str:
        return v.strftime("%H:%M")


class ResourcePage(BaseModel):
    items: list[ResourceOut]
    next_cursor: str | None = None


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: ResourceType
    capacity: int = Field(ge=1)
    slot_minutes: SlotMinutes
    open_time: time
    close_time: time
    timezone: str
    max_slots_per_booking: int = Field(default=4, ge=1)
    max_quantity_per_booking: int = Field(default=1, ge=1)
    policy_name: PolicyName = "FIFO"
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    eligible_groups: list[str] = []


class ResourceUpdate(BaseModel):
    """type, slot_minutes, and timezone are immutable: changing them would invalidate booked slots."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    capacity: int | None = Field(default=None, ge=1)
    open_time: time | None = None
    close_time: time | None = None
    max_slots_per_booking: int | None = Field(default=None, ge=1)
    max_quantity_per_booking: int | None = Field(default=None, ge=1)
    policy_name: PolicyName | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    eligible_groups: list[str] | None = None


class DeactivateBody(BaseModel):
    force: bool = False


class SlotAvailability(BaseModel):
    start_time: datetime
    available: int
    capacity: int


class AvailabilityOut(BaseModel):
    resource_id: UUID
    as_of: datetime
    slot_minutes: int
    slots: list[SlotAvailability]


__all__ = [n for n in dir() if not n.startswith("_")] + ["date"]
