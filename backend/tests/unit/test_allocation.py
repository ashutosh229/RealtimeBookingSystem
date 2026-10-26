from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from app.allocation.base import AllocationContext, Candidate
from app.allocation.fair_share import FairSharePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.metrics import jain_index, mean_ci95, percentile
from app.allocation.registry import POLICIES, policy_by_name
from app.allocation.simulator import Request, SimConfig, generate_trace, simulate

T = datetime(2030, 1, 1, tzinfo=UTC)
FIFO, FAIR = FifoPolicy(), FairSharePolicy()


def cand(i, user, seq, minutes_ago=0):
    return Candidate(id=i, user_id=user, seq=seq, created_at=T - timedelta(minutes=minutes_ago))


def ctx(recent=None):
    return AllocationContext(now=T, recent_allocations=recent or {})


def ids(cands):
    return [c.id for c in cands]


# ---------- policies ----------


def test_fifo_orders_by_sequence_not_by_timestamp():
    cs = [
        cand("b", 1, seq=2, minutes_ago=0),
        cand("a", 2, seq=1, minutes_ago=0),
        cand("c", 3, seq=3, minutes_ago=999),
    ]
    assert ids(FIFO.rank(cs, ctx())) == ["a", "b", "c"]


def test_fair_share_prefers_fewer_recent_allocations():
    cs = [cand("heavy", 1, seq=1), cand("light", 2, seq=2)]
    assert ids(FAIR.rank(cs, ctx({1: 5, 2: 0}))) == ["light", "heavy"]


def test_fair_share_breaks_ties_by_longer_wait_then_sequence():
    cs = [cand("new", 1, seq=1, minutes_ago=1), cand("old", 2, seq=2, minutes_ago=90)]
    assert ids(FAIR.rank(cs, ctx())) == ["old", "new"]  # equal usage: longer wait wins
    same = [cand("x", 1, seq=7, minutes_ago=5), cand("y", 2, seq=4, minutes_ago=5)]
    assert ids(FAIR.rank(same, ctx())) == ["y", "x"]  # equal wait too: lower sequence


@pytest.mark.parametrize("policy", [FIFO, FAIR])
def test_rank_is_pure(policy):
    cs = [cand(i, i % 3, seq=10 - i) for i in range(8)]
    snapshot, c = list(cs), ctx({0: 2})
    first = policy.rank(cs, c)
    assert cs == snapshot and policy.rank(cs, c) == first
    assert sorted(ids(first)) == sorted(ids(cs))


@pytest.mark.parametrize("policy", [FIFO, FAIR])
def test_rank_of_empty_queue(policy):
    assert policy.rank([], ctx()) == []


def test_explain_has_the_decision_inputs():
    e = FAIR.explain(cand("a", 1, seq=3, minutes_ago=2), ctx({1: 4}))
    assert e == {
        "policy": "FAIR_SHARE",
        "recent_allocations": 4,
        "wait_seconds": 120.0,
        "seq": 3,
        "window_days": 14,
    }
    assert FIFO.explain(cand("a", 1, seq=3), ctx())["seq"] == 3


def test_registry():
    assert set(POLICIES) == {"FIFO", "FAIR_SHARE"}
    assert policy_by_name("FAIR_SHARE").version == "1.0"
    with pytest.raises(ValueError):
        policy_by_name("LOTTERY")


# ---------- metrics ----------


def test_jain_bounds():
    assert jain_index([3, 3, 3, 3]) == pytest.approx(1.0)
    assert jain_index([8, 0, 0, 0]) == pytest.approx(0.25)  # 1/n when one user takes everything
    assert jain_index([]) == 1.0 and jain_index([0, 0, 0]) == 1.0
    assert jain_index([4, 1, 1]) == pytest.approx(36 / (3 * 18))


def test_jain_is_scale_invariant():
    assert jain_index([1, 2, 3]) == pytest.approx(jain_index([10, 20, 30]))


def test_percentile_nearest_rank():
    assert percentile([], 95) == 0.0
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5


def test_mean_ci95():
    assert mean_ci95([]) == (0.0, 0.0) and mean_ci95([4.0]) == (4.0, 0.0)
    m, ci = mean_ci95([1.0, 2.0, 3.0])
    assert m == pytest.approx(2.0) and ci == pytest.approx(4.303 * 1.0 / 3**0.5)


# ---------- simulator ----------


def flood(user_counts: dict[int, int]) -> list[Request]:
    return [
        Request(0, u) for u, n in user_counts.items() for _ in range(n)
    ]  # all arrive in round 0, in order


def test_fair_share_beats_fifo_when_one_user_floods():
    trace = flood({0: 4, 1: 1, 2: 1})  # user 0 queued first and often; 4 slots in total
    cfg = SimConfig(rounds=4, capacity=1, patience=100, window_rounds=100)
    fifo, fair = simulate(FIFO, trace, cfg), simulate(FAIR, trace, cfg)
    assert fifo.allocated == Counter({0: 4})
    assert fair.allocated == Counter({0: 2, 1: 1, 2: 1})
    assert fair.metrics["jain_alloc"] == pytest.approx(16 / 18)
    assert fifo.metrics["jain_alloc"] == pytest.approx(1 / 3)
    assert fair.metrics["jain_alloc"] > fifo.metrics["jain_alloc"]


def test_fifo_serves_in_arrival_order():
    trace = [Request(0, 5), Request(0, 6), Request(1, 7)]
    res = simulate(FIFO, trace, SimConfig(rounds=3, capacity=1, patience=10))
    assert res.alloc_per_round == [1, 1, 1] and res.waits == [0, 1, 1]


def test_full_utilization_under_overload():
    res = simulate(
        FIFO,
        flood({u: 10 for u in range(10)}),
        SimConfig(rounds=10, capacity=2, patience=100),
    )
    assert res.alloc_per_round == [2] * 10 and res.metrics["utilization"] == 1.0
    assert res.metrics["success_rate"] == pytest.approx(20 / 100)


def test_requests_expire_after_patience():
    res = simulate(
        FIFO,
        [Request(0, 1), Request(0, 2)],
        SimConfig(rounds=3, capacity=1, patience=0),
    )
    assert sum(res.allocated.values()) == 1 and res.metrics["starvation_rate"] == pytest.approx(0.5)


def test_rolling_window_forgets_old_allocations():
    # user 0 is served in round 0; at round 5 they compete again with a user who has never been served
    trace = [Request(0, 0), Request(5, 0), Request(5, 1)]
    narrow = simulate(FAIR, trace, SimConfig(rounds=6, capacity=1, patience=0, window_rounds=3))
    wide = simulate(FAIR, trace, SimConfig(rounds=6, capacity=1, patience=0, window_rounds=100))
    assert wide.allocated[1] == 1 and wide.allocated[0] == 1  # old win still counts: user 1 first
    assert narrow.allocated[0] == 2 and narrow.allocated[1] == 0  # forgotten: tie -> lower sequence


@pytest.mark.parametrize("policy", [FIFO, FAIR])
def test_conservation_on_a_generated_trace(policy):
    cfg = SimConfig(rounds=30, capacity=5, patience=4)
    res = simulate(policy, generate_trace(50, 30, 5, 3.0, seed=1), cfg)
    assert max(res.alloc_per_round) <= 5
    assert sum(res.alloc_per_round) == sum(res.allocated.values()) == len(res.waits)
    assert all(res.allocated[u] <= res.requested[u] for u in res.requested)
    assert all(0 <= w <= cfg.patience for w in res.waits)
    assert sum(res.requested.values()) == res.total_requests


def test_trace_generation_is_deterministic_and_seeded():
    a, b = generate_trace(40, 20, 4, 2.0, seed=9), generate_trace(40, 20, 4, 2.0, seed=9)
    assert a == b and a != generate_trace(40, 20, 4, 2.0, seed=10)
    assert len(a) == round(2.0 * 4 * 20) and all(
        a[i].round <= a[i + 1].round for i in range(len(a) - 1)
    )


def test_heavy_users_generate_most_of_the_demand():
    trace = generate_trace(100, 100, 50, 4.0, seed=3)  # 20 heavy users, 60% share
    heavy = sum(1 for r in trace if r.user < 20) / len(trace)
    assert 0.55 < heavy < 0.65


def test_simulation_is_reproducible():
    cfg, trace = SimConfig(rounds=20, capacity=3), generate_trace(30, 20, 3, 2.0, seed=5)
    a, b = simulate(FAIR, trace, cfg), simulate(FAIR, trace, cfg)
    assert a.allocated == b.allocated and a.waits == b.waits
