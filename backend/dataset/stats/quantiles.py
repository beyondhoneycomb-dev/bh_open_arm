"""Report the deviation between exact and histogram-approximate quantiles (WP-3D-03).

`compute_stats` estimates quantiles from a histogram (`RunningQuantileStats`), and
`aggregate_stats` count-weights per-episode quantiles — both are approximations.
This computes the EXACT quantiles (`numpy.quantile`) over the same data and reports
the per-channel deviation, so the approximation error is measured rather than
assumed (`02b` §8.1 WP-3D-03: exact-quantile vs histogram-approx deviation report).
It loads a feature's values in full, so it is an offline report, not the streaming
fit path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from backend.dataset.stats.constants import QUANTILE_KEYS, QUANTILE_LEVELS


@dataclass(frozen=True)
class QuantileDeviation:
    """The exact-vs-approximate deviation for one channel at one quantile level.

    Attributes:
        feature: The feature key.
        channel_index: The channel's position.
        level: The quantile level (e.g. 0.99).
        quantile_key: The metric key (e.g. `q99`).
        exact: The exact quantile from `numpy.quantile`.
        approx: The histogram-approximate quantile from the fitted statistics.
        abs_deviation: `abs(exact - approx)`.
    """

    feature: str
    channel_index: int
    level: float
    quantile_key: str
    exact: float
    approx: float
    abs_deviation: float


@dataclass(frozen=True)
class QuantileDeviationReport:
    """The exact-vs-approximate quantile deviations across a fitted table.

    Attributes:
        max_abs_deviation: The largest deviation over every channel and level.
        deviations: Each per-channel, per-level deviation.
    """

    max_abs_deviation: float
    deviations: tuple[QuantileDeviation, ...]


def exact_quantiles(values: np.ndarray) -> dict[str, np.ndarray]:
    """Compute the exact per-channel quantiles for one feature's values.

    Args:
        values: A `(frames, channels)` array of a feature's stored values.

    Returns:
        (dict) Quantile key to the per-channel exact quantile.
    """
    matrix = np.asarray(values, dtype=np.float64).reshape(len(values), -1)
    return {
        key: np.quantile(matrix, level, axis=0)
        for key, level in zip(QUANTILE_KEYS, QUANTILE_LEVELS, strict=True)
    }


def quantile_deviation_report(
    approx: Mapping[str, Mapping[str, np.ndarray]],
    values_by_feature: Mapping[str, np.ndarray],
) -> QuantileDeviationReport:
    """Compare a fitted table's approximate quantiles against exact ones.

    Args:
        approx: Feature key to its fitted metric table (carrying `q01`..`q99`).
        values_by_feature: Feature key to the `(frames, channels)` values the exact
            quantiles are computed over.

    Returns:
        (QuantileDeviationReport) Per-channel, per-level deviations and the maximum.
    """
    deviations: list[QuantileDeviation] = []
    max_abs = 0.0
    for feature, values in values_by_feature.items():
        exact = exact_quantiles(values)
        approx_metrics = approx[feature]
        for key, level in zip(QUANTILE_KEYS, QUANTILE_LEVELS, strict=True):
            exact_channels = np.asarray(exact[key], dtype=np.float64).reshape(-1)
            approx_channels = np.asarray(approx_metrics[key], dtype=np.float64).reshape(-1)
            for channel_index in range(exact_channels.size):
                exact_value = float(exact_channels[channel_index])
                approx_value = float(approx_channels[channel_index])
                abs_dev = abs(exact_value - approx_value)
                max_abs = max(max_abs, abs_dev)
                deviations.append(
                    QuantileDeviation(
                        feature=feature,
                        channel_index=channel_index,
                        level=level,
                        quantile_key=key,
                        exact=exact_value,
                        approx=approx_value,
                        abs_deviation=abs_dev,
                    )
                )
    return QuantileDeviationReport(max_abs_deviation=max_abs, deviations=tuple(deviations))
