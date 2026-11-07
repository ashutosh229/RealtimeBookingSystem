"""E7: gaming attacks (cancel-hoarding and duplicate accounts) against each policy.

python bench/sim/run_gaming.py --quick
"""

import argparse
import json

from _common import aggregate, git_sha, make_out_dir, write_csv

from app.allocation.fair_share import FairSharePolicy
from app.allocation.fair_share_decay import FairShareDecayPolicy
from app.allocation.fair_share_q import FairShareQueuePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.simulator import (
    SimConfig,
    generate_trace,
    heavy_set,
    simulate,
    with_sybils,
)

KEYS = [
    "gamer_share_alloc",
    "honest_success_rate",
    "wasted_rate",
    "utilization",
    "jain_alloc",
    "zero_alloc_rate",
]
POLICIES = {
    "FIFO": FifoPolicy(),
    "FAIR_SHARE": FairSharePolicy(),
    "FAIR_SHARE_Q": FairShareQueuePolicy(2.0),
    "FAIR_SHARE_D": FairShareDecayPolicy(7.0),
}


def scenarios(a) -> list[dict]:
    out = [{"name": "baseline (honest)", "p": 0.0, "counts": True, "k": 1}]
    for p in a.cancel_p:
        out.append(
            {"name": f"cancel p={p}, penalty ON", "p": p, "counts": True, "k": 1}
        )
        out.append(
            {"name": f"cancel p={p}, penalty OFF", "p": p, "counts": False, "k": 1}
        )
    for k in a.sybil_k:
        if k > 1:
            out.append({"name": f"sybil k={k}", "p": 0.0, "counts": True, "k": k})
    return out


def main(a) -> None:
    out = make_out_dir("gaming")
    runs: list[dict] = []
    users = a.users
    capacity = max(1, users // a.users_per_slot)
    owners = heavy_set(users)  # the heavy group is the one that games
    for seed in range(a.seeds):
        base = generate_trace(
            users, a.rounds, capacity, a.ratio, seed, heavy_peak=a.heavy_peak
        )
        for sc in scenarios(a):
            trace, gamers = with_sybils(base, owners, sc["k"], users, seed)
            if sc["k"] == 1:
                gamers = frozenset(owners)
            cfg = SimConfig(
                rounds=a.rounds,
                capacity=capacity,
                patience=a.patience,
                window_rounds=a.window,
                heavy_users=gamers,
                gamers=gamers,
                gamer_cancel_p=sc["p"],
                cancel_counts=sc["counts"],
                cancel_seed=seed,
            )
            for name, policy in POLICIES.items():
                m = simulate(policy, trace, cfg).metrics
                runs.append(
                    {
                        "scenario": sc["name"],
                        "policy": name,
                        "seed": seed,
                        **{k: m[k] for k in KEYS},
                    }
                )
        print(f"done seed={seed}", flush=True)
    write_csv(out / "runs.csv", runs)
    rows = aggregate(runs, ["scenario", "policy"], KEYS)
    write_csv(out / "summary.csv", rows)
    (out / "config.json").write_text(
        json.dumps({**vars(a), "git_sha": git_sha()}, indent=2), encoding="utf-8"
    )
    print(
        f"\n{'scenario':<26} {'policy':<13} {'gamer%':>7} {'honest':>7} {'wasted':>7} {'util':>6}"
    )
    for r in rows:
        print(
            f"{r['scenario']:<26} {r['policy']:<13} {r['gamer_share_alloc']:>7.3f} "
            f"{r['honest_success_rate']:>7.3f} {r['wasted_rate']:>7.3f} {r['utilization']:>6.3f}"
        )
    print(f"\nresults in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--ratio", type=float, default=4.0)
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--users-per-slot", type=int, default=10)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--window", type=int, default=28)
    p.add_argument("--heavy-peak", type=float, default=0.8)
    p.add_argument("--cancel-p", type=float, nargs="+", default=[0.5])
    p.add_argument("--sybil-k", type=int, nargs="+", default=[2, 4, 8])
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    if args.quick:
        args.seeds = 5
    main(args)
