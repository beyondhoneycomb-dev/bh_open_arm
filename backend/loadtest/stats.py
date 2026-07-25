"""Nearest-rank percentiles for the load-test measurements.

A single definition of "the p99 of these samples" so the HOL judge and the stop-path
comparison read the same tail the same way. Nearest-rank (not interpolation) matches
the reused stop-latency bench (`backend.torque_bringup.stop_latency`), so a latency
tail computed here and one computed there mean the same thing.
"""

from __future__ import annotations

from collections.abc import Sequence


def percentile(samples_sec: Sequence[float], pct: float) -> float:
    """Return the given percentile of a sample set by nearest-rank.

    Args:
        samples_sec: The samples; must be non-empty.
        pct: The percentile to take, 0-100.

    Returns:
        (float) The nearest-rank percentile value.

    Raises:
        ValueError: If `samples_sec` is empty — a percentile of nothing is undefined,
            and returning a zero would read as a passing measurement that never ran.
    """
    if not samples_sec:
        raise ValueError("percentile of an empty sample set is undefined")
    ordered = sorted(samples_sec)
    rank = max(1, min(len(ordered), round(pct / 100.0 * len(ordered))))
    return ordered[rank - 1]
