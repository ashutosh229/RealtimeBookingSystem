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
    contention_k: int = 2  # a win is contended if >= k other requests were still waiting after it
    heavy_users: frozenset[int] = frozenset()  # for the heavy-share metrics only


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
    contended: Counter = field(default_factory=Counter)


def heavy_set(users: int, heavy_frac: float = 0.2) -> frozenset[int]:
    """The heavy-user group used by generate_trace: user ids 0..n_heavy-1."""
    return frozenset(range(max(1, round(users * heavy_frac))))


def generate_trace(
    users: int,
    rounds: int,
    capacity: int,
    demand_ratio: float,
    seed: int,
    heavy_frac: float = 0.2,
    heavy_share: float = 0.6,
    heavy_peak: float = 0.0,
    peak_period: int = 10,
    peak_frac: float = 0.2,
) -> list[Request]:
    """demand_ratio = total requests / total capacity. A small group of heavy users sends most requests.

    heavy_peak: probability that a heavy user's request lands in a peak round (the first
    peak_frac of every peak_period rounds) instead of a uniformly random round. 0 keeps the
    original trace for a given seed.
    """
    rng = random.Random(seed)
    n_heavy = len(heavy_set(users, heavy_frac))
    heavy, light = range(n_heavy), range(n_heavy, users)
    peak_rounds = [
        r for r in range(rounds) if r % peak_period < max(1, round(peak_period * peak_frac))
    ]
    total = round(demand_ratio * capacity * rounds)
    reqs = []
    for _ in range(total):
        if heavy_peak <= 0:
            rnd = rng.randrange(rounds)
            pool = heavy if (len(light) == 0 or rng.random() < heavy_share) else light
        else:
            is_heavy = len(light) == 0 or rng.random() < heavy_share
            pool = heavy if is_heavy else light
            rnd = (
                rng.choice(peak_rounds)
                if (is_heavy and rng.random() < heavy_peak)
                else rng.randrange(rounds)
            )
        reqs.append(Request(rnd, rng.choice(pool)))
    reqs.sort(key=lambda r: r.round)  # stable: ties keep generation order
    return reqs


def _window_count(hist: dict[int, deque[int]], user: int, rnd: int, window: int) -> int:
    dq = hist[user]
    while dq and dq[0] <= rnd - window:
        dq.popleft()
    return len(dq)


def simulate(policy: AllocationPolicy, requests: Sequence[Request], cfg: SimConfig) -> SimResult:
    by_round: dict[int, list[Request]] = defaultdict(list)
    for r in requests:
        by_round[r.round].append(r)

    queue: list[Candidate] = []
    arrival: dict[int, int] = {}
    history: dict[int, deque[int]] = defaultdict(deque)  # user -> rounds of past allocations
    contended_hist: dict[int, deque[int]] = defaultdict(deque)  # user -> rounds of contended wins
    requested, allocated, contended = Counter(), Counter(), Counter()
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
        users_now = {c.user_id for c in queue}
        recent = {u: _window_count(history, u, rnd, cfg.window_rounds) for u in users_now}
        recent_c = {u: _window_count(contended_hist, u, rnd, cfg.window_rounds) for u in users_now}

        ctx = AllocationContext(
            now=now,
            recent_allocations=recent,
            window_days=cfg.window_rounds,
            recent_contended=recent_c,
        )
        t0 = time.perf_counter()
        ranked = policy.rank(queue, ctx)
        policy_seconds += time.perf_counter() - t0

        chosen = ranked[: cfg.capacity]
        taken = {c.id for c in chosen}
        for i, c in enumerate(chosen):
            allocated[c.user_id] += 1
            history[c.user_id].append(rnd)
            waits.append(rnd - arrival[c.id])
            if len(ranked) - i - 1 >= cfg.contention_k:  # others were still waiting after this win
                contended[c.user_id] += 1
                contended_hist[c.user_id].append(rnd)
        queue = [c for c in queue if c.id not in taken]
        per_round.append(len(chosen))

    res = SimResult(
        len(requests),
        requested,
        allocated,
        waits,
        per_round,
        cfg,
        policy_seconds,
        contended=contended,
    )
    res.metrics = summarize(res)
    return res


def summarize(res: SimResult) -> dict:
    total_alloc = sum(res.allocated.values())
    total_req = sum(res.requested.values())
    users = list(res.requested)  # only users who asked at least once
    capacity_total = res.config.capacity * res.config.rounds
    heavy = res.config.heavy_users
    heavy_req = sum(n for u, n in res.requested.items() if u in heavy)
    heavy_alloc = sum(n for u, n in res.allocated.items() if u in heavy)
    return {
        "allocated": total_alloc,
        "success_rate": total_alloc / res.total_requests if res.total_requests else 1.0,
        "starvation_rate": (1 - total_alloc / res.total_requests if res.total_requests else 0.0),
        "utilization": total_alloc / capacity_total if capacity_total else 0.0,
        "jain_alloc": jain_index(res.allocated.get(u, 0) for u in users),
        "jain_satisfaction": jain_index(res.allocated.get(u, 0) / res.requested[u] for u in users),
        "zero_alloc_rate": (
            (sum(1 for u in users if res.allocated.get(u, 0) == 0) / len(users)) if users else 0.0
        ),
        "heavy_share_req": heavy_req / total_req if total_req else 0.0,
        "heavy_share_alloc": heavy_alloc / total_alloc if total_alloc else 0.0,
        "wait_mean": sum(res.waits) / len(res.waits) if res.waits else 0.0,
        "wait_p95": percentile(res.waits, 95),
        "wait_max": max(res.waits, default=0),
        "policy_ms": res.policy_seconds * 1000,
    }
