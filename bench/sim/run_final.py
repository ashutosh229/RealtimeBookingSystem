"""C4: final comparison of allocation policies and surge protection on identical traces.

    python bench/sim/run_final.py --quick
    python bench/sim/run_final.py
Output: bench/results/sim-<time>-final_<sha>/{runs.csv, summary.csv, report.md, *.png, config.json}
"""

import argparse
import json

from _common import (
    aggregate,
    git_sha,
    make_out_dir,
    paired_delta,
    pareto_front,
    write_csv,
)

from app.allocation.admission import CreditWallet, TokenBucket
from app.allocation.fair_share import FairSharePolicy
from app.allocation.fair_share_decay import FairShareDecayPolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.simulator import SimConfig, generate_trace, heavy_set, simulate

SCENARIOS = {
    "steady": dict(heavy_peak=0.0, surge_frac=0.0),
    "bursty heavy users": dict(heavy_peak=0.8, surge_frac=0.0),
    "flash crowd": dict(heavy_peak=0.0, surge_frac=0.5),
}
KEYS = [
    "timely_rate",
    "success_rate",
    "utilization",
    "wait_p95",
    "jain_alloc",
    "chance_gini",
    "chance_gap",
    "zero_alloc_rate",
    "heavy_share_alloc",
    "gave_up_rate",
    "queue_peak",
]
BETTER = {
    "timely_rate": 1,
    "success_rate": 1,
    "utilization": 1,
    "wait_p95": -1,
    "jain_alloc": 1,
    "chance_gini": -1,
    "zero_alloc_rate": -1,
    "gave_up_rate": -1,
    "queue_peak": -1,
}
DELTAS = ["timely_rate", "jain_alloc", "chance_gini", "wait_p95"]
BASELINE = "FIFO"


def systems(a) -> dict:
    """label -> (policy, admission factory or None, retries, min_gap)"""

    def bucket():
        return TokenBucket(a.rate, a.burst)

    def wallet():
        return CreditWallet(
            income=a.income, cap=a.credit_cap, surge_k=1.0, max_price=4.0
        )

    fair, decay = FairSharePolicy(), FairShareDecayPolicy(7.0)
    return {
        "FIFO": (FifoPolicy(), None, 0, 0),
        "FAIR_SHARE": (fair, None, 0, 0),
        "FAIR_SHARE_D": (decay, None, 0, 0),
        "FAIR_SHARE + gap3": (fair, None, 0, 3),
        "FIFO + bucket": (FifoPolicy(), bucket, a.retries, 0),
        "FAIR_SHARE + bucket": (fair, bucket, a.retries, 0),
        "FAIR_SHARE + credits": (fair, wallet, a.retries, 0),
    }


def md_table(header: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(header) + " |\n|" + "|".join("---" for _ in header) + "|\n"
    return line + "\n".join("| " + " | ".join(r) + " |" for r in rows) + "\n"


def write_report(out, a, runs, rows) -> None:
    labels = list(dict.fromkeys(r["system"] for r in rows))
    md = [
        "# C4: final comparison\n",
        f"Synthetic traces (demand/capacity = {a.ratio:g}, {a.users} users, {a.rounds} rounds, "
        f"{a.seeds} seeds, same trace for every system). Means over seeds. "
        f"*Timely success* = share of all requests served within {a.timely} rounds.\n",
    ]
    for sc in SCENARIOS:
        by = {r["system"]: r for r in rows if r["scenario"] == sc}
        md.append(f"\n## Scenario: {sc}\n")
        md.append(
            md_table(
                [
                    "system",
                    "timely",
                    "success",
                    "util",
                    "p95 wait",
                    "Jain",
                    "Gini",
                    "zero-seat users",
                    "heavy share",
                    "never admitted",
                    "queue peak",
                ],
                [
                    [
                        s,
                        f"{by[s]['timely_rate']:.3f}",
                        f"{by[s]['success_rate']:.3f}",
                        f"{by[s]['utilization']:.3f}",
                        f"{by[s]['wait_p95']:.1f}",
                        f"{by[s]['jain_alloc']:.3f}",
                        f"{by[s]['chance_gini']:.3f}",
                        f"{by[s]['zero_alloc_rate']:.3f}",
                        f"{by[s]['heavy_share_alloc']:.3f}",
                        f"{by[s]['gave_up_rate']:.3f}",
                        f"{by[s]['queue_peak']:.0f}",
                    ]
                    for s in labels
                ],
            )
        )
        md.append(
            f"\nDifference from {BASELINE} (paired by seed, mean +/- 95% CI; * = interval excludes 0):\n"
        )
        drows = []
        for s in labels:
            if s == BASELINE:
                continue
            cells = []
            for m in DELTAS:
                mean, ci = paired_delta(runs, sc, s, BASELINE, m)
                cells.append(f"{mean:+.3f} +/- {ci:.3f}{'*' if abs(mean) > ci else ''}")
            drows.append([s, *cells])
        md.append(md_table(["system", *DELTAS], drows))
        front = pareto_front(
            {s: (by[s]["timely_rate"], by[s]["jain_alloc"]) for s in labels}
        )
        md.append(
            f"\nPareto frontier (timely success vs Jain index): {', '.join(sorted(front))}\n"
        )
        best = []
        for m, sign in BETTER.items():
            top = max(labels, key=lambda s: sign * by[s][m])
            best.append(f"{m}: {top} ({by[top][m]:.3f})")
        md.append("\nBest per metric: " + "; ".join(best) + "\n")
    md.append(
        "\n## Notes\n- Door-rejected requests count as unserved attempts. `chance_gap` is the light users' "
        "mean chance minus the heavy users', so it is reported but not ranked.\n"
        "- Limiter parameters are identical across systems and not tuned per scenario.\n"
        "- Traces are synthetic; conclusions are about relative behaviour under stated assumptions.\n"
    )
    (out / "report.md").write_text("".join(md), encoding="utf-8")


def plots(out, rows) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scs, labels = list(SCENARIOS), list(dict.fromkeys(r["system"] for r in rows))
    panels = [
        ("timely_rate", "timely success"),
        ("wait_p95", "p95 wait (rounds)"),
        ("jain_alloc", "Jain (counts)"),
        ("chance_gini", "Gini of chance (lower = equal)"),
        ("heavy_share_alloc", "heavy group's seat share"),
        ("gave_up_rate", "never admitted"),
    ]
    fig, axes = plt.subplots(
        len(panels),
        len(scs),
        figsize=(4.8 * len(scs), 2.3 * len(panels)),
        sharex=True,
        squeeze=False,
    )
    for i, (key, title) in enumerate(panels):
        for j, sc in enumerate(scs):
            ax = axes[i][j]
            data = {r["system"]: r for r in rows if r["scenario"] == sc}
            ax.bar(
                range(len(labels)),
                [data[s][key] for s in labels],
                yerr=[data[s][key + "_ci95"] for s in labels],
                capsize=2,
            )
            ax.grid(axis="y", alpha=0.3)
            if i == 0:
                ax.set_title(sc)
            if j == 0:
                ax.set_ylabel(title, fontsize=8)
    for ax in axes[-1]:
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "final_bars.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(scs), figsize=(4.8 * len(scs), 4), squeeze=False)
    for ax, sc in zip(axes[0], scs, strict=True):
        data = {r["system"]: r for r in rows if r["scenario"] == sc}
        pts = {s: (data[s]["timely_rate"], data[s]["jain_alloc"]) for s in labels}
        front = pareto_front(pts)
        for s, (x, y) in pts.items():
            ax.scatter(x, y, marker="o" if s in front else "x")
            ax.annotate(
                s, (x, y), fontsize=7, xytext=(3, 3), textcoords="offset points"
            )
        ax.set(
            title=sc,
            xlabel="timely success (higher is better)",
            ylabel="Jain index (higher is better)",
        )
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "final_pareto.png", dpi=150)
    plt.close(fig)


def main(a) -> None:
    out = make_out_dir("final")
    capacity = max(1, a.users // a.users_per_slot)
    runs = []
    for seed in range(a.seeds):
        for sc, kw in SCENARIOS.items():
            trace = generate_trace(
                a.users,
                a.rounds,
                capacity,
                a.ratio,
                seed,
                surge_start=int(a.rounds * 0.4),
                surge_len=3,
                **kw,
            )
            for label, (policy, factory, retries, gap) in systems(a).items():
                cfg = SimConfig(
                    rounds=a.rounds,
                    capacity=capacity,
                    patience=a.patience,
                    window_rounds=a.window,
                    heavy_users=heavy_set(a.users),
                    admission=factory,
                    max_retries=retries,
                    min_gap=gap,
                    admission_seed=seed,
                )
                res = simulate(policy, trace, cfg)
                m = dict(res.metrics)
                m["timely_rate"] = (
                    sum(1 for w in res.waits if w <= a.timely) / res.total_requests
                    if res.total_requests
                    else 1.0
                )
                runs.append(
                    {
                        "scenario": sc,
                        "system": label,
                        "seed": seed,
                        **{k: m[k] for k in KEYS},
                    }
                )
        print(f"done seed={seed}", flush=True)
    write_csv(out / "runs.csv", runs)
    rows = aggregate(runs, ["scenario", "system"], KEYS)
    write_csv(out / "summary.csv", rows)
    write_report(out, a, runs, rows)
    if not a.no_plots:
        plots(out, rows)
    (out / "config.json").write_text(
        json.dumps({**vars(a), "git_sha": git_sha()}, indent=2), encoding="utf-8"
    )
    print((out / "report.md").read_text(encoding="utf-8"))
    print(f"results in {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, default=200)
    p.add_argument("--ratio", type=float, default=2.0)
    p.add_argument("--seeds", type=int, default=30)
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--users-per-slot", type=int, default=10)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--window", type=int, default=28)
    p.add_argument(
        "--timely",
        type=int,
        default=3,
        help="a request is timely if served within this many rounds",
    )
    p.add_argument("--rate", type=float, default=0.3)
    p.add_argument("--burst", type=float, default=3.0)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--income", type=float, default=0.3)
    p.add_argument("--credit-cap", type=float, default=6.0)
    p.add_argument("--no-plots", action="store_true")
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    if args.quick:
        args.seeds = 5
    main(args)
