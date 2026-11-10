from collections import Counter

import pytest

from app.allocation.fair_share import FairSharePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.metrics import chance_stats, gini
from app.allocation.simulator import Request, SimConfig, simulate


def test_gini_bounds():
    assert gini([1, 1, 1, 1]) == pytest.approx(0.0)
    assert gini([0, 0, 0, 4]) == pytest.approx(0.75)  # (n-1)/n
    assert gini([]) == 0.0 and gini([0, 0]) == 0.0


def test_chance_stats():
    s = chance_stats([0.0, 0.0, 1.0])
    assert s["chance_mean"] == pytest.approx(1 / 3) and s["chance_min"] == 0.0
    assert s["chance_median"] == 0.0 and s["chance_gini"] == pytest.approx(2 / 3)
    assert s["chance_low_share"] == pytest.approx(2 / 3)  # two users below half the mean
    assert chance_stats([])["chance_gini"] == 0.0
    assert chance_stats([0.0, 0.0])["chance_low_share"] == 0.0


def flood(counts):
    return [Request(0, u) for u, n in counts.items() for _ in range(n)]


def test_simulator_chance_metrics_separate_the_policies():
    trace = flood({0: 4, 1: 1, 2: 1})  # user 0 floods; 4 seats in total
    cfg = SimConfig(
        rounds=4,
        capacity=1,
        patience=100,
        window_rounds=100,
        heavy_users=frozenset({0}),
    )
    fifo, fair = simulate(FifoPolicy(), trace, cfg), simulate(FairSharePolicy(), trace, cfg)
    assert fifo.allocated == Counter({0: 4})
    f, g = fifo.metrics, fair.metrics
    assert (f["chance_min"], f["chance_gini"], f["chance_gap"]) == (
        0.0,
        pytest.approx(2 / 3),
        -1.0,
    )
    assert (g["chance_min"], g["chance_gini"], g["chance_gap"]) == (
        0.5,
        pytest.approx(2 / 15),
        0.5,
    )
    assert f["chance_low_share"] == pytest.approx(2 / 3) and g["chance_low_share"] == 0.0
