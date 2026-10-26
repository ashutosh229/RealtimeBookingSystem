from collections.abc import Sequence

from app.allocation.base import AllocationContext, Candidate


class FairSharePolicy:
    name = "FAIR_SHARE"
    version = "1.0"

    @staticmethod
    def _wait_seconds(cand: Candidate, ctx: AllocationContext) -> float:
        return (ctx.now - cand.created_at).total_seconds()

    def rank(self, candidates: Sequence[Candidate], ctx: AllocationContext) -> list[Candidate]:
        def key(c: Candidate):
            return (
                ctx.recent_allocations.get(c.user_id, 0),
                -self._wait_seconds(c, ctx),
                c.seq,
            )

        return sorted(candidates, key=key)

    def explain(self, cand: Candidate, ctx: AllocationContext) -> dict:
        return {
            "policy": self.name,
            "recent_allocations": ctx.recent_allocations.get(cand.user_id, 0),
            "wait_seconds": self._wait_seconds(cand, ctx),
            "seq": cand.seq,
            "window_days": ctx.window_days,
        }
