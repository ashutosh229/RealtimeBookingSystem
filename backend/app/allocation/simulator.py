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
    min_gap: int = 0  # a user may win at most once per `min_gap` rounds (0 = off)


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


def _cooling(last_win: dict[int, int], user: int, rnd: int, min_gap: int) -> bool:
    return min_gap > 0 and user in last_win and rnd - last_win[user] < min_gap


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
    """One round = arrivals, expiry, then up to `capacity` picks, re-ranking after every pick.

    After a pick only the winner's usage changes, so only the winner's remaining requests are
    re-ranked; everyone else keeps the order from the round's first ranking. This equals a full
    re-rank per pick for any policy whose key for a request depends only on that request and its
    user's usage (a brute-force test checks it).
    """
    by_round: dict[int, list[Request]] = defaultdict(list)
    for r in requests:
        by_round[r.round].append(r)

    queue: list[Candidate] = []
    arrival: dict[int, int] = {}
    history: dict[int, deque[int]] = defaultdict(deque)
    contended_hist: dict[int, deque[int]] = defaultdict(deque)
    last_win: dict[int, int] = {}
    requested, allocated, contended = Counter(), Counter(), Counter()
    waits: list[int] = []
    per_round: list[int] = []
    policy_seconds, seq = 0.0, 0

    def timed_rank(cands: list[Candidate], ctx: AllocationContext) -> list[Candidate]:
        nonlocal policy_seconds
        t0 = time.perf_counter()
        out = policy.rank(cands, ctx)
        policy_seconds += time.perf_counter() - t0
        return out

    for rnd in range(cfg.rounds):
        now = _EPOCH + timedelta(days=rnd)
        for r in by_round.get(rnd, []):
            seq += 1
            arrival[seq] = rnd
            requested[r.user] += 1
            queue.append(Candidate(id=seq, user_id=r.user, seq=seq, created_at=now))
        queue = [c for c in queue if rnd - arrival[c.id] <= cfg.patience]  # expire

        eligible = [c for c in queue if not _cooling(last_win, c.user_id, rnd, cfg.min_gap)]
        per_user: dict[int, list[Candidate]] = defaultdict(list)
        for c in eligible:
            per_user[c.user_id].append(c)
        recent = {u: _window_count(history, u, rnd, cfg.window_rounds) for u in per_user}
        recent_c = {u: _window_count(contended_hist, u, rnd, cfg.window_rounds) for u in per_user}
        ctx = AllocationContext(
            now=now,
            recent_allocations=recent,
            window_days=cfg.window_rounds,
            recent_contended=recent_c,
        )

        main = deque(timed_rank(eligible, ctx))
        taken: set[int] = set()
        won: set[int] = set()
        rest_of: dict[int, list[Candidate]] = {}  # users who already won this round
        best_of: dict[int, Candidate] = {}  # their current best remaining request
        waiting = len(eligible)
        chosen = 0
        while chosen < cfg.capacity and waiting > 0:
            while main and (main[0].id in taken or main[0].user_id in won):
                main.popleft()
            contenders = ([main[0]] if main else []) + list(best_of.values())
            if not contenders:
                break
            best = contenders[0] if len(contenders) == 1 else timed_rank(contenders, ctx)[0]

            u = best.user_id
            waiting -= 1  # eligible requests still waiting after this win
            chosen += 1
            taken.add(best.id)
            won.add(u)
            allocated[u] += 1
            history[u].append(rnd)
            waits.append(rnd - arrival[best.id])
            recent[u] = recent.get(u, 0) + 1
            if waiting >= cfg.contention_k:
                contended[u] += 1
                contended_hist[u].append(rnd)
                recent_c[u] = recent_c.get(u, 0) + 1
            last_win[u] = rnd

            rest = [c for c in rest_of.get(u, per_user[u]) if c.id != best.id]
            if (
                cfg.min_gap > 0
            ):  # the winner is now cooling: its other requests cannot win this round
                waiting -= len(rest)
                rest_of[u] = []
                best_of.pop(u, None)
            else:
                rest_of[u] = rest
                if rest:
                    best_of[u] = timed_rank(rest, ctx)[0]  # re-rank with the winner's new usage
                else:
                    best_of.pop(u, None)

        queue = [c for c in queue if c.id not in taken]
        per_round.append(chosen)

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
