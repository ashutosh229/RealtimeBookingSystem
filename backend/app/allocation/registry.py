from app.allocation.base import AllocationPolicy
from app.allocation.fair_share import FairSharePolicy
from app.allocation.fair_share_q import FairShareQueuePolicy
from app.allocation.fifo import FifoPolicy

POLICIES: dict[str, AllocationPolicy] = {
    p.name: p for p in (FifoPolicy(), FairSharePolicy(), FairShareQueuePolicy())
}


def policy_by_name(name: str) -> AllocationPolicy:
    try:
        return POLICIES[name]
    except KeyError:
        raise ValueError(f"unknown allocation policy: {name!r}") from None
