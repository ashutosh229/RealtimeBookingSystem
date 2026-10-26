"""E1: FIFO vs fair-share on identical traces.

    python bench/sim/run_fairness.py --quick            # 5 seeds, a minute
    python bench/sim/run_fairness.py                    # full grid, 30 seeds
Output: bench/results/sim-<timestamp>_<git sha>/{runs.csv, summary.csv, config.json}
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.allocation.metrics import mean_ci95  # noqa: E402
from app.allocation.registry import POLICIES  # noqa: E402
from app.allocation.simulator import SimConfig, generate_trace, simulate  # noqa: E402

KEYS = [
    "jain_alloc",
    "jain_satisfaction",
    "success_rate",
    "wait_mean",
    "wait_p95",
    "wait_max",
    "starvation_rate",
    "utilization",
    "policy_ms",
]


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "nogit"


def main(a) -> None:
    out = (
        Path(__file__).resolve().parents[1]
        / "results"
        / f"sim-{time.strftime('%Y%m%d-%H%M%S')}_{git_sha()}"
    )
    out.mkdir(parents=True)
    seeds = list(range(a.seeds))
    runs: list[dict] = []
    for users in a.users:
        capacity = max(1, users // a.users_per_slot)
        cfg = SimConfig(
            rounds=a.rounds,
            capacity=capacity,
            patience=a.patience,
            window_rounds=a.window,
        )
        for ratio in a.ratios:
            for seed in seeds:
                trace = generate_trace(
                    users, a.rounds, capacity, ratio, seed
                )  # one trace, every policy
                for name, policy in POLICIES.items():
                    m = simulate(policy, trace, cfg).metrics
                    runs.append(
                        {
                            "policy": name,
                            "users": users,
                            "capacity": capacity,
                            "ratio": ratio,
                            "seed": seed,
                            **{k: m[k] for k in KEYS},
                        }
                    )
            print(f"done users={users} ratio={ratio}", flush=True)

    with open(out / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0]))
        w.writeheader()
        w.writerows(runs)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        groups[(r["users"], r["ratio"], r["policy"])].append(r)
    rows = []
    for (users, ratio, policy), rs in sorted(groups.items()):
        row = {"users": users, "ratio": ratio, "policy": policy, "n": len(rs)}
        for k in KEYS:
            m, ci = mean_ci95([r[k] for r in rs])
            row[k], row[k + "_ci95"] = round(m, 4), round(ci, 4)
        rows.append(row)
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "config.json").write_text(
        json.dumps({**vars(a), "git_sha": git_sha()}, indent=2), encoding="utf-8"
    )

    print(
        f"\n{'users':>5} {'ratio':>5} {'policy':<11} {'jain':>13} {'jain_sat':>9} {'wait_p95':>8} {'starv':>6} {'util':>5}"
    )
    for r in rows:
        print(
            f"{r['users']:>5} {r['ratio']:>5} {r['policy']:<11} {r['jain_alloc']:>7.3f}±{r['jain_alloc_ci95']:<5.3f}"
            f" {r['jain_satisfaction']:>9.3f} {r['wait_p95']:>8.1f} {r['starvation_rate']:>6.2f} {r['utilization']:>5.2f}"
        )
    print(f"\nresults in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, nargs="+", default=[50, 200, 1000])
    p.add_argument("--ratios", type=float, nargs="+", default=[0.5, 1, 2, 4, 8])
    p.add_argument("--seeds", type=int, default=30)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument(
        "--users-per-slot",
        type=int,
        default=10,
        help="capacity per round = users // this",
    )
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--window", type=int, default=14)
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    if args.quick:
        args.seeds = 5
    main(args)
