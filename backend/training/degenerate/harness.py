"""The σ_min/δ_min derivation harness — a threshold *rationale*, never a constant.

`02c` §1.3 is explicit that the plan does not pin σ_min/δ_min (`FR-DAT-027` leaves
the lower bound `[결정필요]`): a threshold must come from the real per-channel
statistic distribution, and that distribution does not exist until data is
collected. This module is the harness that produces one, following the plan's
order exactly:

  (1) render a channel-statistic histogram (log10 scale, so a degenerate cluster
      near the eps floor and a normal cluster at O(0.1–10) are both visible);
  (2) look for a valley separating the two clusters;
  (3) if separated, place the threshold at the valley midpoint and record why;
  (4) if not separated, ABANDON the auto-threshold and defer to showing every
      channel's statistic for a human to pick (`detector.channel_statistics`).

This is the direct application of "no target before measurement": the harness
never invents a σ_min, it derives one or declines. `02c` §1.3 SHAPE-IM(3) requires
it to be RE-RUN on Wave 3C real data — the fixture distribution is not the real
one — so every derivation is stamped `needs_real_data_rerun`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from backend.training.degenerate.constants import (
    DOMINANT_GAP_RATIO,
    HISTOGRAM_BIN_COUNT,
    LEROBOT_NORMALIZE_EPS,
    MIN_CHANNELS_FOR_DERIVATION,
    MIN_SEPARATION_DECADES,
    NEEDS_REAL_DATA_RERUN,
)
from backend.training.degenerate.finding import NormMode


@dataclass(frozen=True)
class ThresholdDerivation:
    """The outcome of deriving a threshold from a statistic distribution.

    Attributes:
        norm_mode: The mode the statistics were computed under; a threshold is only
            comparable to statistics of the same mode.
        separated: Whether a degenerate cluster was found separated from a normal
            one by a dominant, wide-enough log-scale valley.
        threshold: The derived σ_min/δ_min at the valley midpoint, or `None` when
            not separated — `None` is the signal to fall back to showing every
            channel (`02c` §1.3 step 4), not a threshold of 0.
        rationale: The human sentence recorded in lineage explaining where the
            threshold came from, or why derivation was declined.
        statistics: The per-channel statistics the derivation was run over, sorted
            ascending — the evidence behind the rationale.
        histogram_counts: Log10-binned counts, the "channel-std histogram".
        histogram_edges: The log10 bin edges, length `len(counts) + 1`.
        needs_real_data_rerun: Always True until a derivation is run on Wave 3C real
            data; a fixture-derived threshold must not be mistaken for a validated one.
    """

    norm_mode: NormMode
    separated: bool
    threshold: float | None
    rationale: str
    statistics: tuple[float, ...]
    histogram_counts: tuple[int, ...]
    histogram_edges: tuple[float, ...]
    needs_real_data_rerun: bool


def _log10_floored(value: float) -> float:
    """Return log10 of a statistic, flooring at the normalizer eps.

    A constant channel has statistic 0, whose log10 is undefined; the normalizer
    already treats such a channel as if its denominator were eps, so flooring the
    statistic at eps before the log places a zero-statistic channel at log10(eps) =
    -8 rather than -inf, which is where the normalizer's behaviour puts it anyway.

    Args:
        value: A per-channel statistic (>= 0 in practice).

    Returns:
        (float) log10(max(value, eps)).
    """
    return math.log10(max(abs(value), LEROBOT_NORMALIZE_EPS))


def _histogram(log_values: Sequence[float]) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Render the log-scale channel-statistic histogram.

    Args:
        log_values: The per-channel log10 statistics.

    Returns:
        (tuple) The bin counts and the bin edges (length counts+1).
    """
    counts, edges = np.histogram(np.asarray(log_values, dtype=float), bins=HISTOGRAM_BIN_COUNT)
    return tuple(int(c) for c in counts), tuple(float(e) for e in edges)


def _valley(sorted_logs: Sequence[float]) -> tuple[bool, float | None, str]:
    """Find the dominant separating valley in a sorted log-statistic list.

    A valley is the largest gap between consecutive sorted log values. It counts as
    a real cluster separation only when it is both WIDE (spans at least
    `MIN_SEPARATION_DECADES`) and DOMINANT (at least `DOMINANT_GAP_RATIO` times the
    median of the other gaps) — a distribution that is merely uneven has no such
    gap and derivation is declined.

    Args:
        sorted_logs: The per-channel log10 statistics, sorted ascending.

    Returns:
        (tuple) whether a valley was found; the threshold (10**midpoint) or None;
            and the rationale sentence.
    """
    gaps = [sorted_logs[i + 1] - sorted_logs[i] for i in range(len(sorted_logs) - 1)]
    widest = max(range(len(gaps)), key=lambda i: gaps[i])
    widest_gap = gaps[widest]

    others = [gaps[i] for i in range(len(gaps)) if i != widest]
    median_other = float(np.median(others)) if others else 0.0

    wide_enough = widest_gap >= MIN_SEPARATION_DECADES
    dominant = median_other <= 0.0 or widest_gap >= DOMINANT_GAP_RATIO * median_other

    if not (wide_enough and dominant):
        return (
            False,
            None,
            (
                f"no separating valley: widest log10 gap {widest_gap:.2f} decades "
                f"(need >= {MIN_SEPARATION_DECADES} and >= {DOMINANT_GAP_RATIO}x the median "
                f"other gap {median_other:.2f}); abandon auto-threshold and show every channel "
                "for a human to pick (02c §1.3 step 4)"
            ),
        )

    low_edge = sorted_logs[widest]
    high_edge = sorted_logs[widest + 1]
    midpoint = (low_edge + high_edge) / 2.0
    threshold = 10.0**midpoint
    low_cluster = widest + 1
    high_cluster = len(sorted_logs) - low_cluster
    rationale = (
        f"threshold at valley midpoint 10**{midpoint:.2f} = {threshold:.3e}: {low_cluster} "
        f"channel(s) below (degenerate cluster, log10 <= {low_edge:.2f}) separated from "
        f"{high_cluster} above (normal cluster, log10 >= {high_edge:.2f}) by a {widest_gap:.2f}-"
        "decade gap"
    )
    return True, threshold, rationale


def derive_threshold(norm_mode: NormMode, statistics: Sequence[float]) -> ThresholdDerivation:
    """Derive a σ_min/δ_min from a channel-statistic distribution, or decline.

    Args:
        norm_mode: The mode the statistics were computed under.
        statistics: Per-channel statistics for that mode, across the dataset(s).

    Returns:
        (ThresholdDerivation) A separated derivation carrying a threshold and its
            rationale, or an unseparated one carrying `threshold=None` and the
            reason it was declined.
    """
    ordered = tuple(sorted(float(s) for s in statistics))
    log_values = [_log10_floored(s) for s in ordered]
    counts, edges = _histogram(log_values) if ordered else ((), ())

    if len(ordered) < MIN_CHANNELS_FOR_DERIVATION:
        return ThresholdDerivation(
            norm_mode=norm_mode,
            separated=False,
            threshold=None,
            rationale=(
                f"only {len(ordered)} channel(s) < {MIN_CHANNELS_FOR_DERIVATION} needed to see a "
                "distribution; abandon auto-threshold and show every channel (02c §1.3 step 4)"
            ),
            statistics=ordered,
            histogram_counts=counts,
            histogram_edges=edges,
            needs_real_data_rerun=NEEDS_REAL_DATA_RERUN,
        )

    separated, threshold, rationale = _valley(log_values)
    return ThresholdDerivation(
        norm_mode=norm_mode,
        separated=separated,
        threshold=threshold,
        rationale=rationale,
        statistics=ordered,
        histogram_counts=counts,
        histogram_edges=edges,
        needs_real_data_rerun=NEEDS_REAL_DATA_RERUN,
    )
