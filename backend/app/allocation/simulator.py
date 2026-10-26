"""Round-based allocation simulator (HLD section 9). One resource pool, unit-size requests.

Each round: arrivals join the queue, over-patient requests expire, then the policy ranks the queue
and the top `capacity` requests are served. The same trace can be replayed under any policy.
"""

import random
import time
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.allocation.base import AllocationContext, AllocationPolicy, Candidate
from app.allocation.metrics import jain_index, percentile

_EPOCH = datetime(2030, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Request:
    round: int
    user: int


@dataclass(frozen=True)
class SimConfig:
    rounds: int
    capacity: int  # units served per round
    patience: int = 10  # a request may wait this many rounds after arrival, then expires
    window_rounds: int = 14  # rolling window for "recent allocations"


@dataclass
class SimResult:
    total_requests: int
    requested: Counter
    allocated: Counter
    waits: list[int]
    alloc_per_round: list[int]
    config: SimConfig
    policy_seconds: float = 0.0
    metrics: dict = field(default_factory=dict)


def generate_trace(
    users: int,
    rounds: int,
    capacity: int,
    demand_ratio: float,
    seed: int,
    heavy_frac: float = 0.2,
    heavy_share: float = 0.6,
) -> list[Request]:
    """demand_ratio = total requests / total capacity. A small group of heavy users sends most requests."""
    rng = random.Random(seed)
    n_heavy = max(1, round(users * heavy_frac))
    heavy, light = range(n_heavy), range(n_heavy, users)
    total = round(demand_ratio * capacity * rounds)
    reqs = []
    for _ in range(total):
        rnd = rng.randrange(rounds)
        pool = heavy if (len(light) == 0 or rng.random() < heavy_share) else light
        reqs.append(Request(rnd, rng.choice(pool)))
    reqs.sort(key=lambda r: r.round)  # stable: ties keep generation order
    return reqs


def simulate(policy: AllocationPolicy, requests: Sequence[Request], cfg: SimConfig) -> SimResult:
    by_round: dict[int, list[Request]] = defaultdict(list)
    for r in requests:
        by_round[r.round].append(r)

    queue: list[Candidate] = []
    arrival: dict[int, int] = {}
    history: dict[int, deque[int]] = defaultdict(deque)  # user -> rounds of past allocations
    requested, allocated = Counter(), Counter()
    waits: list[int] = []
    per_round: list[int] = []
    policy_seconds, seq = 0.0, 0

    for rnd in range(cfg.rounds):
        now = _EPOCH + timedelta(days=rnd)
        for r in by_round.get(rnd, []):
            seq += 1
            arrival[seq] = rnd
            requested[r.user] += 1
            queue.append(Candidate(id=seq, user_id=r.user, seq=seq, created_at=now))

        queue = [c for c in queue if rnd - arrival[c.id] <= cfg.patience]  # expire
        recent: dict[int, int] = {}
        for u in {c.user_id for c in queue}:
            dq = history[u]
            while dq and dq[0] <= rnd - cfg.window_rounds:
                dq.popleft()
            recent[u] = len(dq)

        ctx = AllocationContext(now=now, recent_allocations=recent, window_days=cfg.window_rounds)
        t0 = time.perf_counter()
        ranked = policy.rank(queue, ctx)
        policy_seconds += time.perf_counter() - t0

        chosen = ranked[: cfg.capacity]
        taken = {c.id for c in chosen}
        for c in chosen:
            allocated[c.user_id] += 1
            history[c.user_id].append(rnd)
            waits.append(rnd - arrival[c.id])
        queue = [c for c in queue if c.id not in taken]
        per_round.append(len(chosen))

    res = SimResult(len(requests), requested, allocated, waits, per_round, cfg, policy_seconds)
    res.metrics = summarize(res)
    return res


def summarize(res: SimResult) -> dict:
    total_alloc = sum(res.allocated.values())
    users = list(res.requested)  # only users who asked at least once
    capacity_total = res.config.capacity * res.config.rounds
    return {
        "allocated": total_alloc,
        "success_rate": total_alloc / res.total_requests if res.total_requests else 1.0,
        "starvation_rate": (1 - total_alloc / res.total_requests if res.total_requests else 0.0),
        "utilization": total_alloc / capacity_total if capacity_total else 0.0,
        "jain_alloc": jain_index(res.allocated.get(u, 0) for u in users),
        "jain_satisfaction": jain_index(res.allocated.get(u, 0) / res.requested[u] for u in users),
        "wait_mean": sum(res.waits) / len(res.waits) if res.waits else 0.0,
        "wait_p95": percentile(res.waits, 95),
        "wait_max": max(res.waits, default=0),
        "policy_ms": res.policy_seconds * 1000,
    }
