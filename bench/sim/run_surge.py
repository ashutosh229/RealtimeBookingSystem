"""E8: surge protection. Admission control (token bucket, tail drop, credits) against a flash crowd.

python bench/sim/run_surge.py --quick
python bench/sim/run_surge.py --surge-frac 0      # same scenarios without a flash crowd
"""

import argparse
import json

from _common import aggregate, git_sha, make_out_dir, write_csv

from app.allocation.admission import Chain, CreditWallet, QueueCap, TokenBucket
from app.allocation.fair_share import FairSharePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.simulator import SimConfig, generate_trace, heavy_set, simulate

POLICIES = {"FIFO": FifoPolicy(), "FAIR_SHARE": FairSharePolicy()}
KEYS = [
    "success_rate",
    "utilization",
    "wait_p95",
    "queue_peak",
    "queue_mean",
    "gave_up_rate",
    "gave_up_heavy_share",
    "retries_per_req",
    "jain_alloc",
    "zero_alloc_rate",
    "heavy_share_alloc",
    "chance_gap",
    "chance_min",
]


def scenarios(a, capacity: int) -> dict:
    def bucket():
        return TokenBucket(a.rate, a.burst)

    def cap():
        return QueueCap(a.queue_cap * capacity)

    def wallet():
        return CreditWallet(
            income=a.income,
            cap=a.credit_cap,
            base_price=1.0,
            surge_k=a.surge_k,
            threshold=1.0,
            max_price=a.max_price,
        )

    return {
        "no protection": (None, 0),
        "token bucket": (bucket, 0),
        "token bucket + backoff": (bucket, a.retries),
        "tail drop": (cap, 0),
        "tail drop + bucket + backoff": (lambda: Chain(cap(), bucket()), a.retries),
        "credits (surge price)": (wallet, 0),
        "credits + backoff": (wallet, a.retries),
    }


def main(a) -> None:
    out = make_out_dir("surge")
    capacity = max(1, a.users // a.users_per_slot)
    runs = []
    for seed in range(a.seeds):
        trace = generate_trace(
            a.users,
            a.rounds,
            capacity,
            a.ratio,
            seed,
            heavy_peak=a.heavy_peak,
            surge_frac=a.surge_frac,
            surge_start=a.surge_start,
            surge_len=a.surge_len,
        )
        for label, (factory, retries) in scenarios(a, capacity).items():
            for pname, policy in POLICIES.items():
                cfg = SimConfig(
                    rounds=a.rounds,
                    capacity=capacity,
                    patience=a.patience,
                    window_rounds=a.window,
                    heavy_users=heavy_set(a.users),
                    admission=factory,
                    max_retries=retries,
                    backoff_base=1,
                    backoff_cap=8,
                    admission_seed=seed,
                )
                m = simulate(policy, trace, cfg).metrics
                runs.append(
                    {
                        "scenario": label,
                        "policy": pname,
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
        f"\n{'scenario':<30} {'policy':<11} {'succ':>5} {'util':>5} {'p95':>5} {'qpeak':>6} {'gaveup':>6} "
        f"{'jain':>5} {'zero':>5} {'heavy%':>6} {'gap':>6}"
    )
    for r in rows:
        print(
            f"{r['scenario']:<30} {r['policy']:<11} {r['success_rate']:>5.3f} {r['utilization']:>5.3f} "
            f"{r['wait_p95']:>5.1f} {r['queue_peak']:>6.0f} {r['gave_up_rate']:>6.3f} {r['jain_alloc']:>5.3f} "
            f"{r['zero_alloc_rate']:>5.3f} {r['heavy_share_alloc']:>6.3f} {r['chance_gap']:>6.3f}"
        )
    print(f"\nresults in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--ratio", type=float, default=2.0)
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--users-per-slot", type=int, default=10)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--window", type=int, default=28)
    p.add_argument("--heavy-peak", type=float, default=0.0)
    p.add_argument(
        "--surge-frac",
        type=float,
        default=0.5,
        help="share of all requests in the flash crowd",
    )
    p.add_argument("--surge-start", type=int, default=40)
    p.add_argument("--surge-len", type=int, default=3)
    p.add_argument(
        "--rate", type=float, default=0.3, help="token bucket refill per user per round"
    )
    p.add_argument("--burst", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument(
        "--queue-cap",
        type=float,
        default=5.0,
        help="tail-drop limit in multiples of per-round capacity",
    )
    p.add_argument(
        "--income", type=float, default=0.3, help="credits earned per user per round"
    )
    p.add_argument("--credit-cap", type=float, default=6.0)
    p.add_argument("--surge-k", type=float, default=1.0)
    p.add_argument("--max-price", type=float, default=4.0)
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    if args.quick:
        args.seeds = 5
    main(args)
