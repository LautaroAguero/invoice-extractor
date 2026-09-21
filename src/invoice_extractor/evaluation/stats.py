"""Interval and paired-test statistics (docs/measurement-rules.md §6, design D4). Stdlib only."""

import math
from statistics import NormalDist


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for k successes out of n trials."""
    if n <= 0:
        raise ValueError("a rate over zero documents has no interval")
    if not 0 <= k <= n:
        raise ValueError(f"k must be between 0 and n, got k={k}, n={n}")
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half_width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c.

    Under the null the discordant pairs split evenly, so the smaller count follows Binomial(b + c, 0.5).
    """
    if b < 0 or c < 0:
        raise ValueError("discordant counts cannot be negative")
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2**n)


def percentile(values: list[int] | list[float], q: float) -> int | float:
    """Nearest-rank percentile (q in 0..1): the smallest value with at least a fraction q at or below it."""
    if not values:
        raise ValueError("percentile of an empty sample")
    if not 0 <= q <= 1:
        raise ValueError(f"q must be between 0 and 1, got {q}")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]
