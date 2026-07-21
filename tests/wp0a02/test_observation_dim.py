"""Bimanual observation.state is 48-dim (WP-0A-02).

Acceptance ⑦: the bimanual `observation.state` dimension is asserted to be 48 —
8 motors x 2 arms x {pos, vel, torque} (16 D-8, 10 §2.3). The width is sourced
from the frozen CTR-UNIT layout, so the action schema and the unit contract cannot
disagree about it.
"""

from __future__ import annotations

from contracts.action import (
    BIMANUAL_OBSERVATION_DIM,
    SINGLE_ARM_OBSERVATION_DIM,
    load_schema,
    raw_observation_channels,
    raw_observation_dim,
)


def test_bimanual_observation_is_48() -> None:
    """The bimanual observation.state is exactly 48-dim."""
    assert BIMANUAL_OBSERVATION_DIM == 48
    assert raw_observation_dim(bimanual=True) == 48


def test_bimanual_channel_count_is_48() -> None:
    """The expanded per-index channel list is 48 long, every index unit-tagged."""
    channels = raw_observation_channels(bimanual=True)
    assert len(channels) == 48
    assert all(channel.unit is not None for channel in channels)


def test_single_arm_observation_is_24() -> None:
    """The single-arm observation.state is 24-dim (half of bimanual)."""
    assert SINGLE_ARM_OBSERVATION_DIM == 24
    assert raw_observation_dim(bimanual=False) == 24


def test_schema_declares_48() -> None:
    """The frozen schema's rawObservation channel declares 48 dims."""
    observation = load_schema().channel("rawObservation")
    assert observation is not None
    assert observation.dim == 48
