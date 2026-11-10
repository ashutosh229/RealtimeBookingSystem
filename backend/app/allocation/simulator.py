"""Round-based allocation simulator (HLD section 9). One resource pool, unit-size requests.

Each round: arrivals join the queue, over-patient requests expire, then the policy ranks the queue
and the top `capacity` requests are served. The same trace can be replayed under any policy.
"""

import random
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.allocation.admission import Admission
from app.allocation.base import AllocationContext, AllocationPolicy, Candidate
from app.allocation.metrics import chance_stats, jain_index, percentile

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
    window_rounds: int = 14  # rolling window for "recent allocations" (1 round = 1 day)
    contention_k: int = 2  # a win is contended if >= k other requests were still waiting after it
    heavy_users: frozenset[int] = frozenset()  # for the heavy-share metrics only
    min_gap: int = 0  # a user may win at most once per `min_gap` rounds (0 = off)
    gamers: frozenset[int] = frozenset()  # accounts that cancel-hoard (B4)
    gamer_cancel_p: float = 0.0
    cancel_counts: bool = True
    cancel_seed: int = 0
    admission: Callable[[], Admission] | None = (
        None  # factory: every run gets a fresh controller (C3)
    )
    max_retries: int = 0  # a rejected request retries this many times with exponential backoff
    backoff_base: int = 1  # first retry delay in rounds; doubles per retry, plus random jitter
    backoff_cap: int = 8
    admission_seed: int = 0


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
    wasted: int = 0  # seats won and cancelled too late to be re-offered
    rejected: Counter = field(
        default_factory=Counter
    )  # reason -> door rejections (including retried ones)
    gave_up: Counter = field(default_factory=Counter)  # user -> requests never admitted
    retries: int = 0
    queue_peak: int = 0
    queue_sum: int = 0


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
    surge_frac: float = 0.0,
    surge_start: int = 0,
    surge_len: int = 3,
) -> list[Request]:
    """demand_ratio = total requests / total capacity. A small group of heavy users sends most requests.

    heavy_peak: probability that a heavy user's request lands in a peak round.
    surge_frac: share of ALL requests that land in a flash crowd of surge_len rounds from surge_start.
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
        if surge_frac > 0 and rng.random() < surge_frac:
            rnd = min(rounds - 1, surge_start + rng.randrange(surge_len))
        reqs.append(Request(rnd, rng.choice(pool)))
    reqs.sort(key=lambda r: r.round)  # stable: ties keep generation order
    return reqs


def with_sybils(
    requests: Sequence[Request],
    owners: Iterable[int],
    k: int,
    first_new_id: int,
    seed: int,
) -> tuple[list[Request], frozenset[int]]:
    """Spread each owner's requests over k accounts: the owner's own id plus k-1 new ones.
    Returns the new trace and the set of all accounts belonging to the owners."""
    owners = sorted(set(owners))
    if k <= 1 or not owners:
        return list(requests), frozenset(owners)
    rng = random.Random(seed)
    alias = {
        o: [o] + [first_new_id + i * (k - 1) + j for j in range(k - 1)]
        for i, o in enumerate(owners)
    }
    out = [
        Request(r.round, rng.choice(alias[r.user]) if r.user in alias else r.user) for r in requests
    ]
    return out, frozenset(a for ids in alias.values() for a in ids)


def _window_count(hist: dict[int, deque[int]], user: int, rnd: int, window: int) -> int:
    dq = hist[user]
    while dq and dq[0] <= rnd - window:
        dq.popleft()
    return len(dq)


def simulate(policy: AllocationPolicy, requests: Sequence[Request], cfg: SimConfig) -> SimResult:
    """One round = arrivals (+ retries), admission, expiry, then up to `capacity` picks, re-ranking
    after every pick. With no admission controller this is exactly the earlier behaviour.

    A request keeps its ORIGINAL arrival round for waiting time, patience and queue order, even when
    admitted after retries, so waits are what the user experienced.
    """
    by_round: dict[int, list[Request]] = defaultdict(list)
    for r in requests:
        by_round[r.round].append(r)

    admission = cfg.admission() if cfg.admission else None
    retry_rng = random.Random(cfg.admission_seed)  # separate stream: never touches other randomness
    retry_at: dict[int, list[tuple[int, int, int]]] = defaultdict(
        list
    )  # round -> (user, tries, origin)

    queue: list[Candidate] = []
    arrival: dict[int, int] = {}
    history: dict[int, deque[int]] = defaultdict(deque)
    contended_hist: dict[int, deque[int]] = defaultdict(deque)
    last_win: dict[int, int] = {}
    requested, allocated, contended = Counter(), Counter(), Counter()
    rejected, gave_up = Counter(), Counter()
    waits: list[int] = []
    per_round: list[int] = []
    policy_seconds, seq, wasted, retries = 0.0, 0, 0, 0
    queue_peak = queue_sum = 0
    gamer_rng = random.Random(cfg.cancel_seed)

    def timed_rank(cands: list[Candidate], ctx: AllocationContext) -> list[Candidate]:
        nonlocal policy_seconds
        t0 = time.perf_counter()
        out = policy.rank(cands, ctx)
        policy_seconds += time.perf_counter() - t0
        return out

    for rnd in range(cfg.rounds):
        now = _EPOCH + timedelta(days=rnd)
        attempts: list[tuple[int, int, int]] = []
        for r in by_round.get(rnd, []):
            requested[r.user] += 1
            attempts.append((r.user, 0, rnd))
        attempts += retry_at.pop(rnd, [])
        for user, tries, origin in attempts:
            reason = (
                admission.admit(user, rnd, len(queue), cfg.capacity, seq + 1) if admission else None
            )
            if reason is None:
                seq += 1
                arrival[seq] = origin
                queue.append(
                    Candidate(
                        id=seq,
                        user_id=user,
                        seq=seq,
                        created_at=_EPOCH + timedelta(days=origin),
                    )
                )
                continue
            rejected[reason] += 1
            if tries < cfg.max_retries:
                delay = min(cfg.backoff_cap, cfg.backoff_base * 2**tries)
                nxt = rnd + max(
                    1, delay + retry_rng.randrange(delay + 1)
                )  # exponential backoff + jitter
                if nxt - origin <= cfg.patience and nxt < cfg.rounds:
                    retry_at[nxt].append((user, tries + 1, origin))
                    retries += 1
                    continue
            gave_up[user] += 1

        kept: list[Candidate] = []
        for c in queue:  # expire
            if rnd - arrival[c.id] <= cfg.patience:
                kept.append(c)
            elif admission:
                admission.on_expire(c.id)
        queue = kept
        queue_peak = max(queue_peak, len(queue))
        queue_sum += len(queue)

        eligible = [c for c in queue if not _cooling(last_win, c.user_id, rnd, cfg.min_gap)]
        per_user: dict[int, list[Candidate]] = defaultdict(list)
        for c in eligible:
            per_user[c.user_id].append(c)
        recent = {u: _window_count(history, u, rnd, cfg.window_rounds) for u in per_user}
        recent_c = {u: _window_count(contended_hist, u, rnd, cfg.window_rounds) for u in per_user}
        ages = {u: [float(rnd - x) for x in history[u]] for u in per_user}
        ctx = AllocationContext(
            now=now,
            recent_allocations=recent,
            window_days=cfg.window_rounds,
            recent_contended=recent_c,
            win_ages=ages,
        )

        main = deque(timed_rank(eligible, ctx))
        taken: set[int] = set()
        won: set[int] = set()
        rest_of: dict[int, list[Candidate]] = {}
        best_of: dict[int, Candidate] = {}
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
            waiting -= 1
            chosen += 1
            taken.add(best.id)
            won.add(u)
            if admission:
                admission.on_win(best.id)
            cancelled = (
                u in cfg.gamers
                and cfg.gamer_cancel_p > 0
                and gamer_rng.random() < cfg.gamer_cancel_p
            )
            counted = (not cancelled) or cfg.cancel_counts
            if cancelled:
                wasted += 1
            else:
                allocated[u] += 1
                waits.append(rnd - arrival[best.id])
            if counted:
                history[u].append(rnd)
                recent[u] = recent.get(u, 0) + 1
                ages.setdefault(u, []).append(0.0)
                last_win[u] = rnd
                if waiting >= cfg.contention_k:
                    contended[u] += 1
                    contended_hist[u].append(rnd)
                    recent_c[u] = recent_c.get(u, 0) + 1

            rest = [c for c in rest_of.get(u, per_user[u]) if c.id != best.id]
            if cfg.min_gap > 0 and counted:
                waiting -= len(rest)
                rest_of[u] = []
                best_of.pop(u, None)
            else:
                rest_of[u] = rest
                if rest:
                    best_of[u] = timed_rank(rest, ctx)[0]
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
        wasted=wasted,
        rejected=rejected,
        gave_up=gave_up,
        retries=retries,
        queue_peak=queue_peak,
        queue_sum=queue_sum,
    )
    res.metrics = summarize(res)
    return res


def summarize(res: SimResult) -> dict:
    total_alloc = sum(res.allocated.values())
    total_req = sum(res.requested.values())
    users = list(res.requested)  # only users who asked at least once
    capacity_total = res.config.capacity * res.config.rounds
    heavy, gamers = res.config.heavy_users, res.config.gamers
    heavy_req = sum(n for u, n in res.requested.items() if u in heavy)
    heavy_alloc = sum(n for u, n in res.allocated.items() if u in heavy)
    gamer_alloc = sum(n for u, n in res.allocated.items() if u in gamers)
    honest_req = sum(n for u, n in res.requested.items() if u not in gamers)
    chances = [res.allocated.get(u, 0) / res.requested[u] for u in users]
    heavy_p = [c for u, c in zip(users, chances, strict=True) if u in heavy]
    light_p = [c for u, c in zip(users, chances, strict=True) if u not in heavy]
    chance_gap = (
        sum(light_p) / len(light_p) - sum(heavy_p) / len(heavy_p) if heavy_p and light_p else 0.0
    )
    gave_total = sum(res.gave_up.values())
    gave_heavy = sum(n for u, n in res.gave_up.items() if u in heavy)
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
        "wasted_rate": res.wasted / capacity_total if capacity_total else 0.0,
        "gamer_share_alloc": gamer_alloc / total_alloc if total_alloc else 0.0,
        "honest_success_rate": ((total_alloc - gamer_alloc) / honest_req if honest_req else 1.0),
        "wait_mean": sum(res.waits) / len(res.waits) if res.waits else 0.0,
        "wait_p95": percentile(res.waits, 95),
        "wait_max": max(res.waits, default=0),
        "policy_ms": res.policy_seconds * 1000,
        **chance_stats(chances),
        "chance_gap": chance_gap,  # light users' mean chance minus heavy users'
        "gave_up_rate": gave_total / total_req if total_req else 0.0,  # never admitted
        "gave_up_heavy_share": gave_heavy / gave_total if gave_total else 0.0,
        "reject_events_per_req": (sum(res.rejected.values()) / total_req if total_req else 0.0),
        "retries_per_req": res.retries / total_req if total_req else 0.0,
        "queue_peak": res.queue_peak,
        "queue_mean": res.queue_sum / res.config.rounds if res.config.rounds else 0.0,
    }
