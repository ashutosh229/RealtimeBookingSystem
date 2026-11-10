import csv
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.allocation.metrics import mean_ci95  # noqa: E402


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "nogit"


def make_out_dir(tag: str) -> Path:
    out = (
        Path(__file__).resolve().parents[1]
        / "results"
        / f"sim-{time.strftime('%Y%m%d-%H%M%S')}-{tag}_{git_sha()}"
    )
    out.mkdir(parents=True)
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def aggregate(
    runs: list[dict], group_keys: list[str], metric_keys: list[str]
) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        groups[tuple(r[k] for k in group_keys)].append(r)
    rows = []
    for key, rs in sorted(groups.items()):
        row = dict(zip(group_keys, key, strict=True))
        row["n"] = len(rs)
        for m in metric_keys:
            mean, ci = mean_ci95([r[m] for r in rs])
            row[m], row[m + "_ci95"] = round(mean, 4), round(ci, 4)
        rows.append(row)
    return rows


def paired_delta(
    runs: list[dict], scenario: str, system: str, baseline: str, metric: str
):
    """Mean and 95% CI half-width of (system - baseline) over seeds. Same seeds = same traces."""
    by = {(r["scenario"], r["system"], r["seed"]): r for r in runs}
    seeds = sorted({r["seed"] for r in runs})
    deltas = [
        by[(scenario, system, s)][metric] - by[(scenario, baseline, s)][metric]
        for s in seeds
    ]
    return mean_ci95(deltas)


def pareto_front(points: dict[str, tuple[float, float]]) -> set[str]:
    """Labels not dominated by another point (both coordinates: higher is better)."""
    keep = set()
    for a, (ax, ay) in points.items():
        dominated = any(
            bx >= ax and by >= ay and (bx > ax or by > ay)
            for b, (bx, by) in points.items()
            if b != a
        )
        if not dominated:
            keep.add(a)
    return keep
