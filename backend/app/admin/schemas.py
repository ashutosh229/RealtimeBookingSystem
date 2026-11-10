from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class AttemptOut(BaseModel):
    id: int
    user_id: UUID
    resource_id: UUID
    start_time: datetime
    end_time: datetime
    quantity: int
    waitlist_requested: bool
    outcome: Literal["CONFIRMED", "WAITLISTED", "REJECTED"]
    reason: str | None = None
    detail: str | None = None
    http_status: int
    booking_id: UUID | None = None
    user_group: str
    created_at: datetime


class AttemptPage(BaseModel):
    items: list[AttemptOut]
    next_cursor: str | None = None


class GroupRejection(BaseModel):
    user_group: str
    attempts: int
    rejected: int
    rejection_rate: float


class RejectionSummaryOut(BaseModel):
    window_days: int
    attempts: int
    confirmed: int
    waitlisted: int
    rejected: int
    rejection_rate: float
    users_rejected: int
    by_reason: dict[str, int]
    by_group: list[GroupRejection]
    by_hour_utc: list[int]
