"""Per-user chance of getting a seat, by policy, on identical traces.

python bench/sim/run_chance.py --quick
"""

import argparse
import json

from _common import aggregate, git_sha, make_out_dir, write_csv

from app.allocation.fair_share import FairSharePolicy
from app.allocation.fair_share_decay import FairShareDecayPolicy
from app.allocation.fair_share_q import FairShareQueuePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.metrics import chance_stats
from app.allocation.simulator import SimConfig, generate_trace, heavy_set, simulate

POLICIES = {
    "FIFO": FifoPolicy(),
    "FAIR_SHARE": FairSharePolicy(),
    "FAIR_SHARE_Q": FairShareQueuePolicy(2.0),
    "FAIR_SHARE_D": FairShareDecayPolicy(7.0),
}
KEYS = [
    "chance_mean",
    "chance_min",
    "chance_p10",
    "chance_median",
    "chance_gini",
    "chance_low_share",
    "chance_gap",
    "reg_chance_min",
    "reg_chance_gini",
    "reg_chance_low_share",
    "success_rate",
    "wait_p95",
]


def main(a) -> None:
    out = make_out_dir("chance")
    runs, per_user = [], []
    capacity = max(1, a.users // a.users_per_slot)
    for ratio in a.ratios:
        for seed in range(a.seeds):
            trace = generate_trace(
                a.users, a.rounds, capacity, ratio, seed, heavy_peak=a.heavy_peak
            )
            for name, policy in POLICIES.items():
                cfg = SimConfig(
                    rounds=a.rounds,
                    capacity=capacity,
                    patience=a.patience,
                    window_rounds=a.window,
                    heavy_users=heavy_set(a.users),
                )
                res = simulate(policy, trace, cfg)
                m = res.metrics
                regular = [
                    res.allocated.get(u, 0) / n
                    for u, n in res.requested.items()
                    if n >= a.regular
                ]
                reg = chance_stats(regular)
                runs.append(
                    {
                        "policy": name,
                        "ratio": ratio,
                        "seed": seed,
                        **{k: m[k] for k in KEYS if k in m},
                        "reg_chance_min": reg["chance_min"],
                        "reg_chance_gini": reg["chance_gini"],
                        "reg_chance_low_share": reg["chance_low_share"],
                    }
                )
                for u, n in res.requested.items():
                    per_user.append(
                        {
                            "policy": name,
                            "ratio": ratio,
                            "seed": seed,
                            "user": u,
                            "requests": n,
                            "chance": round(res.allocated.get(u, 0) / n, 4),
                        }
                    )
        print(f"done ratio={ratio}", flush=True)
    write_csv(out / "runs.csv", runs)
    write_csv(out / "chances.csv", per_user)
    rows = aggregate(runs, ["ratio", "policy"], KEYS)
    write_csv(out / "summary.csv", rows)
    (out / "config.json").write_text(
        json.dumps({**vars(a), "git_sha": git_sha()}, indent=2), encoding="utf-8"
    )
    print(
        f"\n{'ratio':>5} {'policy':<13} {'min':>5} {'gini':>6} {'low%':>6} {'gap':>6} {'regMin':>7} {'regGini':>8}"
    )
    for r in rows:
        print(
            f"{r['ratio']:>5} {r['policy']:<13} {r['chance_min']:>5.2f} {r['chance_gini']:>6.3f} "
            f"{r['chance_low_share']:>6.3f} {r['chance_gap']:>6.3f} {r['reg_chance_min']:>7.3f} "
            f"{r['reg_chance_gini']:>8.3f}"
        )
    print(f"\nresults in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--ratios", type=float, nargs="+", default=[1, 2, 4])
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--users-per-slot", type=int, default=10)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--window", type=int, default=28)
    p.add_argument("--heavy-peak", type=float, default=0.8)
    p.add_argument(
        "--regular", type=int, default=3, help="min requests for a 'regular user'"
    )
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    if args.quick:
        args.seeds = 5
    main(args)
