"""E6: allocation-policy variants on identical traces.

python bench/sim/run_variants.py --quick
python bench/sim/run_variants.py --window 28
"""

import argparse
import json

from _common import aggregate, git_sha, make_out_dir, write_csv

from app.allocation.fair_share import FairSharePolicy
from app.allocation.fair_share_decay import FairShareDecayPolicy
from app.allocation.fair_share_q import FairShareQueuePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.simulator import SimConfig, generate_trace, heavy_set, simulate

KEYS = [
    "jain_alloc",
    "jain_satisfaction",
    "zero_alloc_rate",
    "heavy_share_alloc",
    "success_rate",
    "wait_mean",
    "wait_p95",
    "utilization",
    "policy_ms",
]

VARIANTS = {  # label -> (policy, min_gap in rounds)
    "FIFO": (FifoPolicy(), 0),
    "FAIR_SHARE": (FairSharePolicy(), 0),
    "FAIR_SHARE_Q(w=2)": (FairShareQueuePolicy(2.0), 0),
    "FAIR_SHARE_D(h=3)": (FairShareDecayPolicy(3.0), 0),
    "FAIR_SHARE_D(h=7)": (FairShareDecayPolicy(7.0), 0),
    "FAIR_SHARE+gap3": (FairSharePolicy(), 3),
}


def main(a) -> None:
    out = make_out_dir("variants")
    runs: list[dict] = []
    for users in a.users:
        capacity = max(1, users // a.users_per_slot)
        for ratio in a.ratios:
            for seed in range(a.seeds):
                trace = generate_trace(
                    users, a.rounds, capacity, ratio, seed, heavy_peak=a.heavy_peak
                )
                for label, (policy, gap) in VARIANTS.items():
                    cfg = SimConfig(
                        rounds=a.rounds,
                        capacity=capacity,
                        patience=a.patience,
                        window_rounds=a.window,
                        min_gap=gap,
                        heavy_users=heavy_set(users),
                    )
                    m = simulate(policy, trace, cfg).metrics
                    runs.append(
                        {
                            "variant": label,
                            "users": users,
                            "ratio": ratio,
                            "seed": seed,
                            **{k: m[k] for k in KEYS},
                        }
                    )
            print(f"done users={users} ratio={ratio}", flush=True)
    write_csv(out / "runs.csv", runs)
    rows = aggregate(runs, ["users", "ratio", "variant"], KEYS)
    write_csv(out / "summary.csv", rows)
    (out / "config.json").write_text(
        json.dumps({**vars(a), "git_sha": git_sha()}, indent=2), encoding="utf-8"
    )
    print(
        f"\n{'users':>5} {'ratio':>5} {'variant':<20} {'jain':>6} {'zero':>6} {'heavy%':>7} {'p95':>5} {'succ':>5}"
    )
    for r in rows:
        print(
            f"{r['users']:>5} {r['ratio']:>5} {r['variant']:<20} {r['jain_alloc']:>6.3f} "
            f"{r['zero_alloc_rate']:>6.3f} {r['heavy_share_alloc']:>7.3f} {r['wait_p95']:>5.1f} {r['success_rate']:>5.3f}"
        )
    print(f"\nresults in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, nargs="+", default=[200])
    p.add_argument("--ratios", type=float, nargs="+", default=[1, 2, 4])
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--users-per-slot", type=int, default=10)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument(
        "--window",
        type=int,
        default=28,
        help="same window for every variant (about 4 half-lives)",
    )
    p.add_argument(
        "--heavy-peak",
        type=float,
        default=0.8,
        help="share of heavy requests landing in peak rounds",
    )
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    if args.quick:
        args.seeds = 5
    main(args)
