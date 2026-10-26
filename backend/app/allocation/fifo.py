from collections.abc import Sequence

from app.allocation.base import AllocationContext, Candidate


class FifoPolicy:
    name = "FIFO"
    version = "1.0"

    def rank(self, candidates: Sequence[Candidate], ctx: AllocationContext) -> list[Candidate]:
        return sorted(candidates, key=lambda c: c.seq)

    def explain(self, cand: Candidate, ctx: AllocationContext) -> dict:
        return {"policy": self.name, "seq": cand.seq}
