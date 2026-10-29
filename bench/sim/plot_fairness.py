"""Plots from a sim-* results folder:  python bench/sim/plot_fairness.py bench/results/sim-<folder>"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PANELS = [
    ("jain_alloc", "Jain index (allocation counts)"),
    ("jain_satisfaction", "Jain index (served share of own requests)"),
    ("wait_p95", "p95 wait (rounds, served requests)"),
    ("success_rate", "Success rate"),
]


def main(folder: Path) -> None:
    rows = list(csv.DictReader(open(folder / "summary.csv", encoding="utf-8")))
    users = sorted({int(r["users"]) for r in rows})
    for key, title in PANELS:
        fig, axes = plt.subplots(
            1, len(users), figsize=(4.2 * len(users), 3.6), sharey=True
        )
        for ax, u in zip(axes, users, strict=True):
            series = defaultdict(list)
            for r in rows:
                if int(r["users"]) == u:
                    series[r["policy"]].append(
                        (float(r["ratio"]), float(r[key]), float(r[key + "_ci95"]))
                    )
            for policy, pts in sorted(series.items()):
                pts.sort()
                ax.errorbar(
                    [p[0] for p in pts],
                    [p[1] for p in pts],
                    yerr=[p[2] for p in pts],
                    marker="o",
                    capsize=3,
                    label=policy,
                )
            ax.set_xscale("log", base=2)
            ax.set_xlabel("demand / capacity")
            ax.set_title(f"{u} users")
            ax.grid(alpha=0.3)
        axes[0].set_ylabel(title)
        axes[-1].legend()
        fig.tight_layout()
        fig.savefig(folder / f"{key}.png", dpi=150)
        plt.close(fig)
        print("wrote", folder / f"{key}.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
