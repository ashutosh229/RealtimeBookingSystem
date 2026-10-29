from collections.abc import Hashable, Sequence

from app.allocation.base import AllocationContext, Candidate


class FairShareQueuePolicy:
    """Fair-share where wins gained under contention weigh `weight` times (B1).

    usage = recent + (weight - 1) * recent_contended; rank by (usage, longest wait, queue order).
    weight=1 is plain fair-share.
    """

    name = "FAIR_SHARE_Q"
    version = "1.0"

    def __init__(self, weight: float = 2.0) -> None:
        if weight < 1:
            raise ValueError("weight must be >= 1")
        self.weight = weight

    def usage(self, user: Hashable, ctx: AllocationContext) -> float:
        return ctx.recent_allocations.get(user, 0) + (self.weight - 1.0) * ctx.recent_contended.get(
            user, 0
        )

    def rank(self, candidates: Sequence[Candidate], ctx: AllocationContext) -> list[Candidate]:
        def key(c: Candidate):
            return (
                self.usage(c.user_id, ctx),
                -(ctx.now - c.created_at).total_seconds(),
                c.seq,
            )

        return sorted(candidates, key=key)

    def explain(self, cand: Candidate, ctx: AllocationContext) -> dict:
        return {
            "policy": self.name,
            "recent_allocations": ctx.recent_allocations.get(cand.user_id, 0),
            "recent_contended": ctx.recent_contended.get(cand.user_id, 0),
            "weight": self.weight,
            "usage": self.usage(cand.user_id, ctx),
            "wait_seconds": (ctx.now - cand.created_at).total_seconds(),
            "seq": cand.seq,
            "window_days": ctx.window_days,
        }
