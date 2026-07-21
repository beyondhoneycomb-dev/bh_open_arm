"""Acceptance ③ — normalization statistics split by unit-tag channel group.

③ requires the statistics to be produced per channel group (deg / deg-per-sec /
Nm) rather than one statistic over the mixed 48-dim vector, and requires the
mixed-single-statistic path to warn. The layout is the interleaved one from the
frozen unit contract, so this suite also proves the groups are the interleaved
indices, not contiguous blocks.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from backend.learning.channel_groups import group_indices_by_unit, state_channels
from backend.learning.normalization_stats import (
    MixedUnitStatWarning,
    compute_channel_group_stats,
    pooled_stats_over_vector,
)
from backend.learning.synthetic_dataset import SyntheticDatasetSpec, generate_state_action_arrays


def test_groups_are_the_three_units_interleaved() -> None:
    """The 48-dim state splits into three 16-channel groups, interleaved."""
    channels = state_channels(bimanual=True, use_velocity_and_torque=True)
    groups = group_indices_by_unit(channels)
    assert set(groups) == {"Deg", "DegPerSec", "Nm"}
    assert all(len(indices) == 16 for indices in groups.values())
    # Interleaved, not blocked: position channels are 0, 3, 6, ... not 0..15.
    assert groups["Deg"][:3] == [0, 3, 6]
    assert groups["DegPerSec"][:3] == [1, 4, 7]
    assert groups["Nm"][:3] == [2, 5, 8]


def test_stats_are_separated_by_channel_group() -> None:
    """Each unit group yields its own statistics over only its own indices."""
    spec = SyntheticDatasetSpec(seed=1)
    channels = state_channels(bimanual=True, use_velocity_and_torque=True)
    states, _ = generate_state_action_arrays(spec)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the correct path must not warn
        stats = compute_channel_group_stats(states, channels)

    assert set(stats) == {"Deg", "DegPerSec", "Nm"}
    for unit, group in stats.items():
        assert all(channels[i].unit_name == unit for i in group.indices)
        assert group.count == 16 * states.shape[0]
        assert len(group.per_index_mean) == 16

    # The groups have visibly different scales; pooling them would be dominated by
    # the widest, which is the whole point of separating.
    assert stats["DegPerSec"].std > stats["Deg"].std > stats["Nm"].std


def test_mixed_single_statistic_warns() -> None:
    """③ pooling one statistic over the mixed vector emits MixedUnitStatWarning."""
    spec = SyntheticDatasetSpec(seed=2)
    channels = state_channels(bimanual=True, use_velocity_and_torque=True)
    states, _ = generate_state_action_arrays(spec)

    with pytest.warns(MixedUnitStatWarning):
        pooled = pooled_stats_over_vector(states, channels)
    assert pooled.unit_name == "mixed"


def test_single_unit_vector_does_not_warn() -> None:
    """A position-only (single-unit) vector pools without a warning."""
    spec = SyntheticDatasetSpec(seed=3)
    action_channels = state_channels(bimanual=True, use_velocity_and_torque=False)
    _, actions = generate_state_action_arrays(spec)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        pooled = pooled_stats_over_vector(actions, action_channels)
    assert pooled.unit_name == "Deg"


def test_group_stats_reject_width_mismatch() -> None:
    """A data matrix whose width disagrees with the channels is rejected."""
    channels = state_channels(bimanual=True, use_velocity_and_torque=True)
    with pytest.raises(ValueError, match="channels were declared"):
        compute_channel_group_stats(np.zeros((4, 24)), channels)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
