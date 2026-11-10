import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bench" / "sim"))
import _common  # noqa: E402


def test_pareto_front():
    pts = {"a": (1.0, 1.0), "b": (2.0, 0.5), "c": (0.5, 0.5)}
    assert _common.pareto_front(pts) == {"a", "b"}  # c is dominated by a
    assert _common.pareto_front({"x": (1, 1), "y": (1, 1)}) == {
        "x",
        "y",
    }  # ties are both kept
    assert _common.pareto_front({}) == set()


def test_paired_delta_matches_the_t_interval():
    runs = []
    for seed, value in enumerate([1.0, 2.0, 3.0]):
        runs.append({"scenario": "s", "system": "base", "seed": seed, "m": 0.0})
        runs.append({"scenario": "s", "system": "x", "seed": seed, "m": value})
    mean, ci = _common.paired_delta(runs, "s", "x", "base", "m")
    assert mean == pytest.approx(2.0) and ci == pytest.approx(4.303 / 3**0.5)
    same = _common.paired_delta(runs, "s", "base", "base", "m")
    assert same == (0.0, 0.0)
