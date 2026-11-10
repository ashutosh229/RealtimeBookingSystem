"""python bench/sim/plot_chance.py bench/results/sim-<...>-chance_<sha>"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main(folder: Path) -> None:
    data = defaultdict(list)
    for r in csv.DictReader(open(folder / "chances.csv", encoding="utf-8")):
        data[(float(r["ratio"]), r["policy"])].append(float(r["chance"]))
    ratios = sorted({k[0] for k in data})
    fig, axes = plt.subplots(
        1, len(ratios), figsize=(4.4 * len(ratios), 3.8), sharey=True, squeeze=False
    )
    for ax, ratio in zip(axes[0], ratios, strict=True):
        for (r, pol), vals in sorted(data.items()):
            if r == ratio:
                xs = sorted(vals)
                ax.step(
                    xs,
                    [(i + 1) / len(xs) for i in range(len(xs))],
                    where="post",
                    label=pol,
                )
        ax.set(title=f"demand/capacity = {ratio:g}", xlabel="per-user chance of a seat")
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("share of users with chance <= x")
    axes[0][-1].legend()
    fig.tight_layout()
    fig.savefig(folder / "chance_cdf.png", dpi=150)
    print("wrote", folder / "chance_cdf.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
