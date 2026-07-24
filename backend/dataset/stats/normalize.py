"""Build a normalizer from TRAIN-only statistics — the normalization-input sink (WP-3D-03).

`build_normalizer` is the one place a fitted statistic becomes a normalization
parameter, and it accepts only a `NormalizationStats` (train). A `DiagnosticStats`
is a different type the signature rejects, and `staticcheck` additionally forbids a
diagnostic value from ever reaching this call — the two together are what make
WP-3D-03 ① ("split-local statistics are diagnostic only, never a normalization
input") a checked property rather than a convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from backend.dataset.stats.fit import NormalizationStats


class NormalizationMode(Enum):
    """How a channel is normalized from its statistics."""

    MEAN_STD = "mean_std"
    MIN_MAX = "min_max"


@dataclass(frozen=True)
class Normalizer:
    """Per-feature affine normalization parameters: `(value - center) / scale`.

    Attributes:
        mode: The mode the parameters were derived under.
        center: Feature key to per-channel center (mean, or min).
        scale: Feature key to per-channel scale (std, or `max - min`).
    """

    mode: NormalizationMode
    center: dict[str, np.ndarray]
    scale: dict[str, np.ndarray]


def build_normalizer(stats: NormalizationStats, mode: NormalizationMode) -> Normalizer:
    """Derive normalization parameters from train-only statistics.

    Only a `NormalizationStats` is accepted: a diagnostic (split-local) statistic is
    a different type and cannot be passed here (WP-3D-03 ①). A std or range of zero is
    left as-is rather than silently floored — `stdfloor.detect_std_floor_violations` is
    what surfaces those channels, and hiding them here would defeat that detection.

    Args:
        stats: The train-only normalization statistics.
        mode: MEAN_STD or MIN_MAX.

    Returns:
        (Normalizer) Per-feature center and scale.
    """
    center: dict[str, np.ndarray] = {}
    scale: dict[str, np.ndarray] = {}
    for feature, metrics in stats.per_feature.items():
        if mode is NormalizationMode.MEAN_STD:
            center[feature] = np.asarray(metrics["mean"], dtype=np.float64)
            scale[feature] = np.asarray(metrics["std"], dtype=np.float64)
        else:
            low = np.asarray(metrics["min"], dtype=np.float64)
            high = np.asarray(metrics["max"], dtype=np.float64)
            center[feature] = low
            scale[feature] = high - low
    return Normalizer(mode=mode, center=center, scale=scale)
