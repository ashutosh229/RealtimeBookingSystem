from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from app.allocation.base import AllocationContext, Candidate
from app.allocation.fair_share import FairSharePolicy
from app.allocation.fair_share_decay import FairShareDecayPolicy
from app.allocation.simulator import (
    Request,
    SimConfig,
    generate_trace,
    heavy_set,
    simulate,
    with_sybils,
)

T = datetime(2030, 1, 1, tzinfo=UTC)
FAIR, FD = FairSharePolicy(), FairShareDecayPolicy(7.0)


def cand(i, user, seq, minutes_ago=0):
    return Candidate(id=i, user_id=user, seq=seq, created_at=T - timedelta(minutes=minutes_ago))


def ctx(ages):
    return AllocationContext(
        now=T, recent_allocations={u: len(a) for u, a in ages.items()}, win_ages=ages
    )


def ids(cands):
    return [c.id for c in cands]


def flood(counts):
    return [Request(0, u) for u, n in counts.items() for _ in range(n)]


# ---------- B3: decayed history ----------


def test_decay_weights():
    assert FD.usage(1, ctx({1: [0.0]})) == pytest.approx(1.0)
    assert FD.usage(1, ctx({1: [7.0]})) == pytest.approx(0.5)
    assert FD.usage(1, ctx({1: [0.0, 14.0]})) == pytest.approx(1.25)
    assert FD.usage(9, ctx({})) == 0.0


def test_old_win_outranks_recent_win_when_counts_tie():
    cs = [cand("recent", 1, seq=1), cand("old", 2, seq=2)]
    c = ctx({1: [0.0], 2: [10.0]})
    assert ids(FD.rank(cs, c)) == ["old", "recent"]
    assert ids(FAIR.rank(cs, c)) == [
        "recent",
        "old",
    ]  # plain counts tie, so queue order decides


def test_decay_validation_and_explain():
    with pytest.raises(ValueError):
        FairShareDecayPolicy(0)
    e = FD.explain(cand("a", 1, seq=3, minutes_ago=2), ctx({1: [7.0, 0.0]}))
    assert (e["policy"], e["wins_in_window"], e["half_life"]) == (
        "FAIR_SHARE_D",
        2,
        7.0,
    )
    assert e["usage"] == pytest.approx(1.5)


def test_decay_policy_runs_in_the_simulator_and_conserves():
    cfg = SimConfig(rounds=30, capacity=5, patience=4, window_rounds=28)
    trace = generate_trace(50, 30, 5, 3.0, seed=1, heavy_peak=0.8)
    a, b = simulate(FD, trace, cfg), simulate(FD, trace, cfg)
    assert a.allocated == b.allocated and max(a.alloc_per_round) <= 5
    assert all(a.allocated[u] <= a.requested[u] for u in a.requested)


# ---------- B4: cancel-hoarding ----------


def gaming_cfg(**over):
    base = dict(
        rounds=1,
        capacity=2,
        patience=100,
        window_rounds=100,
        gamers=frozenset({0}),
        gamer_cancel_p=1.0,
    )
    return SimConfig(**{**base, **over})


def test_unpenalised_cancelling_lets_a_gamer_hoard_every_seat():
    trace = flood({0: 3, 1: 1})
    res = simulate(FAIR, trace, gaming_cfg(cancel_counts=False))
    assert res.wasted == 2 and sum(res.allocated.values()) == 0 and res.alloc_per_round == [2]
    m = res.metrics
    assert m["wasted_rate"] == 1.0 and m["honest_success_rate"] == 0.0


def test_penalty_makes_the_cancelled_win_count_so_others_get_a_seat():
    trace = flood({0: 3, 1: 1})
    res = simulate(FAIR, trace, gaming_cfg(cancel_counts=True))
    assert res.wasted == 1 and res.allocated == Counter({1: 1})
    assert res.metrics["honest_success_rate"] == 1.0 and res.metrics["gamer_share_alloc"] == 0.0


def test_gaming_seats_are_conserved_and_default_path_is_untouched():
    trace = generate_trace(50, 30, 5, 3.0, seed=2, heavy_peak=0.8)
    gamers = heavy_set(50)
    res = simulate(
        FAIR,
        trace,
        SimConfig(
            rounds=30,
            capacity=5,
            patience=4,
            gamers=gamers,
            gamer_cancel_p=0.5,
            cancel_counts=False,
        ),
    )
    assert sum(res.alloc_per_round) == sum(res.allocated.values()) + res.wasted
    plain = simulate(FAIR, trace, SimConfig(rounds=30, capacity=5, patience=4))
    other = simulate(
        FAIR,
        trace,
        SimConfig(
            rounds=30,
            capacity=5,
            patience=4,
            gamers=frozenset({999}),
            gamer_cancel_p=1.0,
        ),
    )
    assert plain.allocated == other.allocated and plain.waits == other.waits


# ---------- B4: duplicate accounts ----------


def test_sybils_split_an_owners_requests_across_new_accounts():
    base = generate_trace(40, 30, 4, 3.0, seed=3)
    owners = heavy_set(40)
    trace, accounts = with_sybils(base, owners, k=3, first_new_id=40, seed=3)
    assert len(trace) == len(base) and [r.round for r in trace] == [r.round for r in base]
    assert len(accounts) == len(owners) * 3 and owners <= accounts
    new_ids = {r.user for r in trace if r.user >= 40}
    assert new_ids and new_ids <= accounts
    for r0, r1 in zip(base, trace, strict=True):  # non-owners are untouched
        if r0.user not in owners:
            assert r1.user == r0.user
    assert with_sybils(base, owners, k=3, first_new_id=40, seed=3)[0] == trace


def test_one_account_per_owner_changes_nothing():
    base = generate_trace(20, 10, 2, 2.0, seed=4)
    trace, accounts = with_sybils(base, heavy_set(20), k=1, first_new_id=20, seed=4)
    assert trace == base and accounts == heavy_set(20)
