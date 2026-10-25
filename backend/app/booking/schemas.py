from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

Status = Literal["REQUESTED", "CONFIRMED", "WAITLISTED", "CANCELLED", "COMPLETED", "EXPIRED"]


class BookingCreate(BaseModel):
    resource_id: UUID
    start_time: AwareDatetime
    end_time: AwareDatetime
    quantity: int = Field(default=1, ge=1)
    waitlist_if_full: bool = False


class BookingOut(BaseModel):
    booking_id: UUID
    status: Status
    resource_id: UUID
    start_time: datetime
    end_time: datetime
    quantity: int
    waitlist_position: int | None = None
    waitlist_id: UUID | None = None
    expires_at: datetime | None = None
    created_at: datetime
