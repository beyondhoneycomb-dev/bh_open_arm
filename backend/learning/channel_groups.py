"""Index-to-unit map for the flattened `observation.state` vector.

LeRobot flattens every motor channel into one `observation.state` array, mixing
degrees (`.pos`), degrees-per-second (`.vel`) and newton-metres (`.torque`) in a
single vector (`10` §2.3, `16` D-8). The layout is *interleaved*, not blocked:
index 0 is `left_joint_1.pos` (deg), index 1 is `left_joint_1.vel` (deg/s), index
2 is `left_joint_1.torque` (Nm), index 3 is `left_joint_2.pos`, and so on. A
normalization statistic that pools the whole vector therefore averages degrees
with newton-metres, which is meaningless — this module exists so that every
consumer can split the vector by unit before it computes any statistic.

The layout is not invented here: it is read from the frozen `CTR-UNIT@v1`
declaration through `contracts.units.observation`, so a change to the contract
moves this map with it rather than leaving a second, drifting copy.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.action import BIMANUAL_ACTION_DIM, SINGLE_ARM_ACTION_DIM
from contracts.units.observation import observation_state_units

# The two physical channel suffixes that only appear when velocity and torque are
# recorded. Position is always present; these are dropped when
# `use_velocity_and_torque=False` collapses the state to position-only (`10`
# FR-TRN-074).
_VELOCITY_TORQUE_SUFFIXES = ("vel", "torque")
_POSITION_SUFFIX = "pos"


@dataclass(frozen=True)
class StateChannel:
    """One index of the flattened `observation.state` vector.

    Attributes:
        index: Position in the flattened vector, contiguous from zero.
        name: The LeRobot `names`-array entry, e.g. `left_joint_1.pos`.
        unit_name: The frozen unit tag, one of `Deg` / `DegPerSec` / `Nm`.
    """

    index: int
    name: str
    unit_name: str


def state_channels(
    bimanual: bool = True, use_velocity_and_torque: bool = True
) -> tuple[StateChannel, ...]:
    """Build the ordered channel list for a state-vector configuration.

    Args:
        bimanual: True for the 48/16-dim two-arm layout, False for the 24/8-dim
            single-arm layout.
        use_velocity_and_torque: True keeps the interleaved pos/vel/torque layout
            (`10` §2.3); False keeps position channels only, re-indexed
            contiguously so the vector matches a position-only recording.

    Returns:
        (tuple[StateChannel, ...]) One channel per vector index, in order.
    """
    source = observation_state_units(bimanual=bimanual)
    if use_velocity_and_torque:
        return tuple(
            StateChannel(index=channel.index, name=channel.name, unit_name=channel.unit_name)
            for channel in source
        )

    # Position-only: keep the `.pos` channels and re-index them contiguously, so
    # the result is a valid 0..n-1 vector rather than the sparse indices the full
    # layout would leave behind.
    kept = [channel for channel in source if channel.suffix == _POSITION_SUFFIX]
    return tuple(
        StateChannel(index=new_index, name=channel.name, unit_name=channel.unit_name)
        for new_index, channel in enumerate(kept)
    )


def action_channels(bimanual: bool = True) -> tuple[StateChannel, ...]:
    """Build the channel list for the position-only `action` vector.

    The action is position-only regardless of the observation configuration
    (`10` FR-TRN-074, FR-TRN-066): a policy predicts positions, never velocities
    or torques, so the action vector is always a single-unit (degree) group. Its
    dimension is the frozen `CTR-ACT@v1` `acceptedPositionAction` width (WP-0A-02),
    so the position channels derived from the observation layout are checked
    against the contract rather than trusted to agree with it by coincidence.

    Args:
        bimanual: True for the 16-dim two-arm action, False for the 8-dim
            single-arm action.

    Returns:
        (tuple[StateChannel, ...]) One channel per action index, in order.

    Raises:
        ValueError: If the observation-derived position width disagrees with the
            frozen action-schema dimension.
    """
    channels = state_channels(bimanual=bimanual, use_velocity_and_torque=False)
    expected = BIMANUAL_ACTION_DIM if bimanual else SINGLE_ARM_ACTION_DIM
    if len(channels) != expected:
        raise ValueError(
            f"position-only channel count {len(channels)} disagrees with the frozen "
            f"CTR-ACT@v1 action dimension {expected}"
        )
    return channels


def group_indices_by_unit(channels: tuple[StateChannel, ...]) -> dict[str, list[int]]:
    """Map each unit tag to the vector indices that carry it.

    Args:
        channels: The ordered channel list to partition.

    Returns:
        (dict[str, list[int]]) Unit name to its ascending index list. The key set
        is exactly the distinct units present, so a position-only vector yields a
        single `Deg` group and the 48-dim vector yields `Deg`/`DegPerSec`/`Nm`.
    """
    groups: dict[str, list[int]] = {}
    for channel in channels:
        groups.setdefault(channel.unit_name, []).append(channel.index)
    return groups
