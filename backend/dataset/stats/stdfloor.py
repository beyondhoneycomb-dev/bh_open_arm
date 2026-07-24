"""Detect standard-deviation-floor violations in fitted statistics (WP-3D-03 ③).

A channel that barely moves has std close to zero, and MEAN_STD normalization
divides by it — so a stationary `.vel` (a joint that never moved) or a non-contact
`.torque` (a joint that never loaded) explodes the normalized value, and MIN_MAX
does the same when `max - min` collapses (`02b` §8.2 WP-3D-03 ③). This flags those
channels against a caller-supplied floor and names each one, tagging the
`.pos`/`.vel`/`.torque` suffix so an operator sees which kind of channel is stuck.
The floor is decision-needed — measured then regression-locked — so it is a
parameter here, never a baked target.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from backend.dataset.stats.fit import DiagnosticStats, NormalizationStats
from contracts.recorder import PER_MOTOR_SUFFIXES_FULL

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StdFloorViolation:
    """One channel whose fitted std falls below the floor.

    Attributes:
        feature: The feature key (`action`/`observation.state`).
        channel_index: The channel's position in the feature vector.
        channel_name: The channel name from `names`, or "" when unavailable.
        suffix: The `.pos`/`.vel`/`.torque` suffix of the channel, or None.
        std: The fitted standard deviation of the channel.
    """

    feature: str
    channel_index: int
    channel_name: str
    suffix: str | None
    std: float


@dataclass(frozen=True)
class StdFloorReport:
    """The std-floor scan over a fitted statistics table.

    Attributes:
        floor: The threshold applied.
        violations: Every channel below the floor, in (feature, channel) order.
    """

    floor: float
    violations: tuple[StdFloorViolation, ...]

    @property
    def ok(self) -> bool:
        """Whether no channel fell below the floor."""
        return not self.violations


def _suffix_of(name: str) -> str | None:
    """Return the per-motor suffix a channel name carries, if any."""
    for suffix in PER_MOTOR_SUFFIXES_FULL:
        if name.endswith(suffix):
            return suffix
    return None


def detect_std_floor_violations(
    stats: NormalizationStats | DiagnosticStats,
    names: Mapping[str, Sequence[str]],
    floor: float,
) -> StdFloorReport:
    """Flag every channel whose fitted std is below the floor, and warn on each.

    Args:
        stats: The fitted statistics to scan (normalization or diagnostic).
        names: Feature key to its channel `names`, for naming a flagged channel.
        floor: The provisional std floor; a channel below it is flagged and warned.

    Returns:
        (StdFloorReport) The floor and the flagged channels.
    """
    violations: list[StdFloorViolation] = []
    for feature, metrics in stats.per_feature.items():
        std = np.asarray(metrics["std"], dtype=np.float64).reshape(-1)
        feature_names = list(names.get(feature, ()))
        for index in np.nonzero(std < floor)[0]:
            channel_index = int(index)
            channel_name = (
                feature_names[channel_index] if channel_index < len(feature_names) else ""
            )
            violation = StdFloorViolation(
                feature=feature,
                channel_index=channel_index,
                channel_name=channel_name,
                suffix=_suffix_of(channel_name),
                std=float(std[channel_index]),
            )
            violations.append(violation)
            logger.warning(
                "std-floor violation: %s[%d] %r std=%.3e < floor=%.3e",
                feature,
                channel_index,
                channel_name,
                violation.std,
                floor,
            )
    return StdFloorReport(floor=floor, violations=tuple(violations))
