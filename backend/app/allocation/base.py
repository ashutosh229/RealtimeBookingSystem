"""Policy interface shared by the live promoter and the simulator. No database, no I/O."""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    id: Hashable  # booking_id in production, an int in the simulator
    user_id: Hashable
    seq: int  # server-assigned admission order (never trust client timestamps)
    created_at: datetime
    quantity: int = 1


@dataclass(frozen=True)
class AllocationContext:
    now: datetime
    recent_allocations: Mapping[Hashable, int]  # user_id -> allocations inside the rolling window
    window_days: int = 14


class AllocationPolicy(Protocol):
    name: str
    version: str

    def rank(self, candidates: Sequence[Candidate], ctx: AllocationContext) -> list[Candidate]:
        """Best first. Must not mutate its inputs or touch anything outside them."""

    def explain(self, cand: Candidate, ctx: AllocationContext) -> dict:
        """Decision inputs stored in allocation_records.inputs (invariant I7)."""
