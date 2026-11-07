from collections.abc import Hashable, Sequence

from app.allocation.base import AllocationContext, Candidate


class FairShareDecayPolicy:
    """Fair-share with exponentially decayed history (B3).

    usage = sum over wins in the window of 0.5 ** (age_days / half_life); rank by
    (usage, longest wait, queue order). Smooths the cliff of a hard rolling window.
    """

    name = "FAIR_SHARE_D"
    version = "1.0"

    def __init__(self, half_life: float = 7.0) -> None:
        if half_life <= 0:
            raise ValueError("half_life must be > 0")
        self.half_life = half_life

    def usage(self, user: Hashable, ctx: AllocationContext) -> float:
        return sum(0.5 ** (a / self.half_life) for a in ctx.win_ages.get(user, ()))

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
            "usage": self.usage(cand.user_id, ctx),
            "wins_in_window": len(ctx.win_ages.get(cand.user_id, ())),
            "half_life": self.half_life,
            "wait_seconds": (ctx.now - cand.created_at).total_seconds(),
            "seq": cand.seq,
            "window_days": ctx.window_days,
        }
