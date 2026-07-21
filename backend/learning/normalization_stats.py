"""Normalization statistics split by unit-tag channel group.

`16` D-8 records the trap: the bimanual `observation.state` mixes degrees and
newton-metres in one 48-dim vector, so a normalization statistic taken over the
whole vector pools quantities with different physical dimensions and different
scales. The result is a single mean/std that normalizes torque channels against a
degree scale (and vice versa), which silently corrupts training input.

This module computes statistics *per unit group* — every degree channel together,
every degree-per-second channel together, every newton-metre channel together —
and never one statistic over the mixed vector. The mixed-vector path exists only
as `pooled_stats_over_vector`, and it emits `MixedUnitStatWarning` whenever the
indices it is asked to pool span more than one unit, so the anti-pattern is loud
rather than silent.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from backend.learning.channel_groups import StateChannel, group_indices_by_unit


class MixedUnitStatWarning(UserWarning):
    """A statistic was requested over indices that carry more than one unit.

    Pooling degrees with newton-metres produces a number with no physical
    meaning; the warning names the units that were mixed so the caller can split
    the vector first.
    """


@dataclass(frozen=True)
class ChannelGroupStats:
    """Pooled and per-index statistics for one unit group.

    The pooled fields (`mean`/`std`/`min`/`max`) are scalars over every value of
    every channel in the group — the group-level normalization scale. The
    per-index arrays keep the element-wise statistics LeRobot uses, so a consumer
    that normalizes element-wise still gets exactly one unit's values per index.

    Attributes:
        unit_name: The frozen unit tag this group carries, e.g. `Deg`.
        indices: Vector indices belonging to this group, ascending.
        count: Number of samples pooled (frames times channels in the group).
        mean: Pooled mean over the group.
        std: Pooled population standard deviation over the group.
        minimum: Pooled minimum over the group.
        maximum: Pooled maximum over the group.
        per_index_mean: Element-wise mean, one entry per index in `indices`.
        per_index_std: Element-wise population std, one entry per index.
    """

    unit_name: str
    indices: tuple[int, ...]
    count: int
    mean: float
    std: float
    minimum: float
    maximum: float
    per_index_mean: tuple[float, ...]
    per_index_std: tuple[float, ...]


def compute_channel_group_stats(
    data: npt.NDArray[np.float64], channels: tuple[StateChannel, ...]
) -> dict[str, ChannelGroupStats]:
    """Compute normalization statistics separately for each unit group.

    Args:
        data: Sample matrix of shape `(n_frames, dim)`; column `i` is vector
            index `i`.
        channels: The ordered channel list describing every column's unit.

    Returns:
        (dict[str, ChannelGroupStats]) Unit name to its statistics. The key set is
        exactly the distinct units in `channels`, so nothing pools across units.

    Raises:
        ValueError: If `data` is not 2-D or its width does not match `channels`.
    """
    matrix = np.asarray(data, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError(f"data must be 2-D (n_frames, dim); got shape {matrix.shape}")
    if matrix.shape[1] != len(channels):
        raise ValueError(
            f"data has {matrix.shape[1]} columns but {len(channels)} channels were declared"
        )

    stats: dict[str, ChannelGroupStats] = {}
    for unit_name, indices in group_indices_by_unit(channels).items():
        columns = matrix[:, indices]
        pooled = columns.reshape(-1)
        stats[unit_name] = ChannelGroupStats(
            unit_name=unit_name,
            indices=tuple(indices),
            count=int(pooled.size),
            mean=float(pooled.mean()),
            std=float(pooled.std()),
            minimum=float(pooled.min()),
            maximum=float(pooled.max()),
            per_index_mean=tuple(float(value) for value in columns.mean(axis=0)),
            per_index_std=tuple(float(value) for value in columns.std(axis=0)),
        )
    return stats


def pooled_stats_over_vector(
    data: npt.NDArray[np.float64], channels: tuple[StateChannel, ...]
) -> ChannelGroupStats:
    """Pool one statistic over the whole vector — the anti-pattern D-8 forbids.

    This exists so the mistake can be demonstrated and detected, not so it can be
    used: whenever the supplied channels span more than one unit it emits
    `MixedUnitStatWarning` before returning. Callers wanting a valid statistic use
    `compute_channel_group_stats` instead.

    Args:
        data: Sample matrix of shape `(n_frames, dim)`.
        channels: The ordered channel list describing every column's unit.

    Returns:
        (ChannelGroupStats) The pooled statistic, labelled `mixed` when more than
        one unit was pooled.

    Raises:
        ValueError: If `data` is not 2-D or its width does not match `channels`.
    """
    matrix = np.asarray(data, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError(f"data must be 2-D (n_frames, dim); got shape {matrix.shape}")
    if matrix.shape[1] != len(channels):
        raise ValueError(
            f"data has {matrix.shape[1]} columns but {len(channels)} channels were declared"
        )

    units = sorted(group_indices_by_unit(channels))
    if len(units) > 1:
        warnings.warn(
            f"single statistic pooled over mixed units {units}: degrees and "
            "newton-metres have different scales, so this normalization statistic "
            "is physically meaningless (16 D-8). Split by channel group first.",
            MixedUnitStatWarning,
            stacklevel=2,
        )

    pooled = matrix.reshape(-1)
    unit_label = units[0] if len(units) == 1 else "mixed"
    return ChannelGroupStats(
        unit_name=unit_label,
        indices=tuple(range(len(channels))),
        count=int(pooled.size),
        mean=float(pooled.mean()),
        std=float(pooled.std()),
        minimum=float(pooled.min()),
        maximum=float(pooled.max()),
        per_index_mean=tuple(float(value) for value in matrix.mean(axis=0)),
        per_index_std=tuple(float(value) for value in matrix.std(axis=0)),
    )
