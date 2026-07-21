"""LeRobot soft joint limits as the override source (01 FR-SYS-016, 09 FR-SIM-080).

The jnt_range override that FR-SIM-080 mandates writes *LeRobot's* soft limits into
the MJCF, so those limits must come from LeRobot itself — inventing a second copy
here would be the exact "two sources of one number" divergence NORM-004 exists to
prevent. This module reads ``LEFT_DEFAULT_JOINTS_LIMITS`` /
``RIGHT_DEFAULT_JOINTS_LIMITS`` straight from the pinned LeRobot follower config and
exposes them per side, in degrees, as the single upstream truth.

LeRobot speaks degrees and ``openarm_control`` speaks radians (01 FR-SYS-016), so
every value that crosses into the model does so through the one sanctioned CTR-UNIT
crossing (``contracts.units.conversions.deg_to_rad``); there is no bare
``math.radians`` here. The LeRobot limit dict keys ``joint_1..joint_7`` map to the
MJCF ``openarm_{side}_joint1..joint7`` arm joints, and ``gripper`` maps to
``openarm_{side}_finger_joint1`` — the arm joints are what IK solves and
``ConfigurationLimit`` constrains; the gripper is carried too so the override covers
every joint LeRobot limits (FR-SIM-080 acceptance ②, "all joints").
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.units.conversions import deg_to_rad
from contracts.units.tags import Deg, Rad

# LeRobot limit-dict keys in canonical joint order: seven arm joints then the
# gripper. The order is the contract with the 16-dim action layout, so it is named
# once here rather than re-spelled at each call site.
ARM_JOINT_KEYS = ("joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6", "joint_7")
GRIPPER_KEY = "gripper"

# LeRobot key -> MJCF joint-name suffix. The arm keys index by number; the gripper
# key names the finger driver joint (its mirror is equality-constrained).
_MJCF_SUFFIX = {
    "joint_1": "joint1",
    "joint_2": "joint2",
    "joint_3": "joint3",
    "joint_4": "joint4",
    "joint_5": "joint5",
    "joint_6": "joint6",
    "joint_7": "joint7",
    GRIPPER_KEY: "finger_joint1",
}

SIDES = ("right", "left")


@dataclass(frozen=True)
class JointLimit:
    """One joint's soft limit, carried in both units so no call site re-converts.

    Attributes:
        mjcf_joint: The fully-qualified MJCF joint name this limit is written onto.
        lower_deg: Lower bound in LeRobot degrees (the upstream value).
        upper_deg: Upper bound in LeRobot degrees.
        lower_rad: Lower bound in radians (the model / IK unit).
        upper_rad: Upper bound in radians.
    """

    mjcf_joint: str
    lower_deg: Deg
    upper_deg: Deg
    lower_rad: Rad
    upper_rad: Rad


def _lerobot_side_limits(side: str) -> dict[str, tuple[float, float]]:
    """Return LeRobot's per-side default soft-limit dict in degrees.

    Imported lazily so the module carries no import-time dependency on the robot
    stack; only a caller that actually resolves limits pulls LeRobot in.

    Args:
        side: ``"right"`` or ``"left"``.

    Returns:
        (dict[str, tuple[float, float]]) LeRobot joint key to ``(lo_deg, hi_deg)``.

    Raises:
        ValueError: When ``side`` is neither "right" nor "left".
    """
    from lerobot.robots.openarm_follower.config_openarm_follower import (
        LEFT_DEFAULT_JOINTS_LIMITS,
        RIGHT_DEFAULT_JOINTS_LIMITS,
    )

    if side == "right":
        return dict(RIGHT_DEFAULT_JOINTS_LIMITS)
    if side == "left":
        return dict(LEFT_DEFAULT_JOINTS_LIMITS)
    raise ValueError(f"side must be 'right' or 'left', got {side!r}")


def soft_limits(side: str, arm_prefix: str = "openarm_") -> tuple[JointLimit, ...]:
    """Resolve LeRobot soft limits for one arm, arm joints first then gripper.

    Each returned limit carries both the LeRobot degrees and the radians the model
    is written in; the radians are produced by the single CTR-UNIT ``deg_to_rad``
    crossing, never a bare conversion.

    Args:
        side: ``"right"`` or ``"left"``.
        arm_prefix: MJCF joint-name prefix (``openarm_`` for the v2 asset).

    Returns:
        (tuple[JointLimit, ...]) One entry per LeRobot-limited joint, in
        ``ARM_JOINT_KEYS`` order followed by the gripper.
    """
    side_limits = _lerobot_side_limits(side)
    resolved: list[JointLimit] = []
    for key in (*ARM_JOINT_KEYS, GRIPPER_KEY):
        lo_deg, hi_deg = side_limits[key]
        lower_deg = Deg(lo_deg)
        upper_deg = Deg(hi_deg)
        resolved.append(
            JointLimit(
                mjcf_joint=f"{arm_prefix}{side}_{_MJCF_SUFFIX[key]}",
                lower_deg=lower_deg,
                upper_deg=upper_deg,
                lower_rad=deg_to_rad(lower_deg),
                upper_rad=deg_to_rad(upper_deg),
            )
        )
    return tuple(resolved)


def arm_soft_limits(side: str, arm_prefix: str = "openarm_") -> tuple[JointLimit, ...]:
    """Resolve only the seven arm-joint soft limits IK actually solves for.

    Args:
        side: ``"right"`` or ``"left"``.
        arm_prefix: MJCF joint-name prefix.

    Returns:
        (tuple[JointLimit, ...]) The seven arm-joint limits, joint1..joint7.
    """
    return soft_limits(side, arm_prefix)[: len(ARM_JOINT_KEYS)]


def all_soft_limits(arm_prefix: str = "openarm_") -> tuple[JointLimit, ...]:
    """Resolve LeRobot soft limits for both arms.

    Args:
        arm_prefix: MJCF joint-name prefix.

    Returns:
        (tuple[JointLimit, ...]) Right-arm limits followed by left-arm limits.
    """
    resolved: list[JointLimit] = []
    for side in SIDES:
        resolved.extend(soft_limits(side, arm_prefix))
    return tuple(resolved)
