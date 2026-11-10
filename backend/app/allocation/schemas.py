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


class ChanceGroup(BaseModel):
    user_group: str
    users: int
    mean_chance: float


class ChanceSummaryOut(BaseModel):
    window_days: int
    users: int
    attempts: int
    chance_mean: float
    chance_min: float
    chance_p10: float
    chance_median: float
    chance_gini: float
    chance_low_share: float
    by_group: list[ChanceGroup]
    histogram: list[int]


class MyChanceOut(BaseModel):
    window_days: int
    attempts: int
    successes: int
    my_chance: float | None = None
    cohort_users: int
    cohort_median: float | None = None
    cohort_mean: float | None = None
