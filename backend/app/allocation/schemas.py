from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class WaitlistEntryOut(BaseModel):
    waitlist_id: UUID
    booking_id: UUID
    resource_id: UUID
    status: Literal["ACTIVE", "PROMOTED", "CANCELLED", "EXPIRED"]
    position: int | None = None
    position_is_estimate: bool = False
    start_time: datetime
    end_time: datetime


class WaitlistPage(BaseModel):
    items: list[WaitlistEntryOut]
    next_cursor: str | None = None


class AllocationRecordOut(BaseModel):
    id: int
    booking_id: UUID
    policy_name: str
    policy_version: str
    decision_type: Literal["ADMIT", "PROMOTE", "REJECT_FULL", "SKIP_INELIGIBLE"]
    inputs: dict
    reason: str | None = None
    decided_at: datetime


class AllocationPage(BaseModel):
    items: list[AllocationRecordOut]
    next_cursor: str | None = None


class WaitSeconds(BaseModel):
    mean: float
    p95: float
    max: float


class MetricsSummaryOut(BaseModel):
    window_days: int
    utilization: float
    jain_index: float
    waitlist_length: int
    wait_seconds: WaitSeconds
