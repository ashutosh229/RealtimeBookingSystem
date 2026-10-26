import math
from collections.abc import Iterable, Sequence


def jain_index(values: Iterable[float]) -> float:
    """(sum x)^2 / (n * sum x^2). 1.0 means perfectly equal. Empty or all-zero input counts as equal."""
    xs = list(values)
    if not xs:
        return 1.0
    squares = sum(x * x for x in xs)
    if squares == 0:
        return 1.0
    return sum(xs) ** 2 / (len(xs) * squares)


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile. Empty input gives 0.0."""
    if not values:
        return 0.0
    xs = sorted(values)
    return xs[max(0, math.ceil(p / 100 * len(xs)) - 1)]


_T975 = [
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
]  # two-sided 95% t critical values for df 1..30


def mean_ci95(values: Sequence[float]) -> tuple[float, float]:
    """(mean, half-width of the 95% confidence interval) using Student's t."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    m = sum(values) / n
    if n == 1:
        return m, 0.0
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))
    t = _T975[n - 2] if n - 1 <= len(_T975) else 1.96
    return m, t * sd / math.sqrt(n)
