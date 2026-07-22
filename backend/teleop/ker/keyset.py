"""The KER action keyset, derived from the frozen action schema (WP-3B-14).

The teleoperator's `action_features` and every `get_action()` dict are built here so
the KER never invents a keyset: the position channels come from `openarm_action_
features` (CTR-PLUG@v1) and the honest-zero velocity/torque columns from the same
`raw_observation_channels` (CTR-ACT@v1) the follower's schema uses. Keeping this in
one place is what lets `build_dataset_frame` index a KER action by the follower's
names with no missing key (05 §2.5).

No inverse kinematics happens here or anywhere in this package: the joint angles the
KER reads ARE the position command, so `ker_action` is a name-to-angle zip, not a
solve (FR-TEL-064).
"""

from __future__ import annotations

from collections.abc import Sequence

from contracts.action.observation import raw_observation_channels
from contracts.plugin.robot_abc import openarm_action_features
from contracts.teleop import POSITION_SUFFIX, ZERO_NON_POSITION_VALUE

# LeRobot feature dicts map a channel name to the scalar sample type; every KER
# channel is a float (degrees for `.pos`, an honest zero for `.vel`/`.torque`).
_SCALAR_FEATURE_TYPE = float


class KerKeysetError(ValueError):
    """Raised when a joint-angle vector does not fit the KER position keyset."""


def position_channel_names(bimanual: bool) -> tuple[str, ...]:
    """Return the ordered `.pos` channel names for the KER action.

    Args:
        bimanual: Whether to name the 16 bimanual position channels or 8 single-arm.

    Returns:
        (tuple[str, ...]) Position channel names in motor order.
    """
    return tuple(openarm_action_features(bimanual=bimanual))


def ker_action_features(bimanual: bool, use_velocity_and_torque: bool) -> dict[str, type]:
    """Return the KER `action_features` dict.

    Args:
        bimanual: Whether the keyset is bimanual (16 position) or single-arm (8).
        use_velocity_and_torque: When true, the keyset carries the honest-zero
            `.vel`/`.torque` columns the follower records; when false it is the
            position-only training target.

    Returns:
        (dict[str, type]) Channel name to scalar feature type.
    """
    if not use_velocity_and_torque:
        return openarm_action_features(bimanual=bimanual)
    return {
        channel.name: _SCALAR_FEATURE_TYPE
        for channel in raw_observation_channels(bimanual=bimanual)
    }


def ker_action(
    joint_angles_deg: Sequence[float],
    bimanual: bool,
    use_velocity_and_torque: bool,
) -> dict[str, float]:
    """Map KER joint angles directly onto the action keyset — no IK (FR-TEL-064).

    Each position channel receives the corresponding joint angle in degrees, in motor
    order; every velocity and torque channel receives the honest zero (the KER has no
    torque source and `send_action` hardcodes them, 05 §2.5).

    Args:
        joint_angles_deg: Joint angles in degrees, one per position channel, in motor
            order (left joints then left gripper, then right).
        bimanual: Whether the keyset is bimanual (16) or single-arm (8).
        use_velocity_and_torque: Whether the honest-zero columns are emitted.

    Returns:
        (dict[str, float]) One float per `action_features` key.

    Raises:
        KerKeysetError: If the joint-angle count does not match the position keyset.
    """
    positions = position_channel_names(bimanual)
    if len(joint_angles_deg) != len(positions):
        raise KerKeysetError(
            f"KER read {len(joint_angles_deg)} joint angle(s) but the "
            f"{'bimanual' if bimanual else 'single-arm'} keyset has {len(positions)} "
            "position channel(s)"
        )
    angle_by_channel = dict(zip(positions, joint_angles_deg, strict=True))
    action: dict[str, float] = {}
    for name in ker_action_features(bimanual, use_velocity_and_torque):
        if name.endswith(POSITION_SUFFIX):
            action[name] = float(angle_by_channel[name])
        else:
            action[name] = ZERO_NON_POSITION_VALUE
    return action
