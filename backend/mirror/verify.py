"""Independent verification of the mirror convention (WP-2D-08 acceptance).

Checks that do not trust the convention by re-reading its own constants:

- ``involution_error`` mirrors a vector twice and returns the max deviation from the
  input; FR-MAN-046 requires 0.0 exactly.
- ``convention_matches_pinned_limits`` confirms, per arm joint, that the mirror sign is
  the sign carrying that joint's pinned *right* limit onto its pinned *left* limit
  (reused ``sim.ik.arm_soft_limits``). joint4's limits are identical on both sides, so
  only same-sign matches — flipping joint4 breaks the match, which is the FR-MAN-046
  FAIL_BLOCKING guard proven against the upstream limits rather than asserted.

The gripper is deliberately excluded from the limit cross-check: LeRobot's left-gripper
soft limit ships the mirror bug (both bounds non-positive, FR-MAN-017), so the pinned
left limit is not a valid oracle. ``gripper_mirror_opposes_lerobot_bug`` states that
divergence directly — our mirror opens the left gripper the way LeRobot's limit forbids.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.mirror.constants import ARM_JOINT_COUNT, ARM_MIRROR_SIGNS, GRIPPER_OPEN_RAD
from backend.mirror.convention import mirror_gripper, mirror_q_urdf

Interval = tuple[float, float]


def involution_error(q_urdf: np.ndarray) -> float:
    """Return the max absolute deviation of ``mirror(mirror(q))`` from ``q``.

    Args:
        q_urdf: An eight-value driver vector.

    Returns:
        (float) The worst per-element deviation; 0.0 for a correct involution.
    """
    q = np.asarray(q_urdf, dtype=float)
    round_trip = mirror_q_urdf(mirror_q_urdf(q))
    return float(np.abs(round_trip - q).max())


def _mirror_interval(interval: Interval, sign: float) -> Interval:
    """Reflect a ``(lower, upper)`` interval by a mirror sign.

    A negative sign maps ``[lo, hi]`` to ``[-hi, -lo]``; a positive sign is identity.
    """
    lo, hi = interval
    return (lo, hi) if sign > 0 else (-hi, -lo)


@dataclass(frozen=True)
class JointLimitAgreement:
    """Whether one arm joint's mirror sign agrees with its pinned limits.

    Attributes:
        joint_index: 0-based arm joint index.
        sign: The FR-MAN-046 mirror sign applied to this joint.
        right_interval: The pinned right-side ``(lo, hi)`` in radians.
        left_interval: The pinned left-side ``(lo, hi)`` in radians.
        matches: Whether the right interval mirrored by ``sign`` equals the left interval.
    """

    joint_index: int
    sign: float
    right_interval: Interval
    left_interval: Interval
    matches: bool


def convention_matches_pinned_limits() -> tuple[JointLimitAgreement, ...]:
    """Cross-check every arm-joint mirror sign against the pinned per-side limits.

    Returns:
        (tuple[JointLimitAgreement, ...]) One entry per arm joint, joint1..joint7.
    """
    # Imported here, not at module scope: reaching sim.ik loads the IK/sim stack (the
    # optional [robot] group), and the pure convention core must import without it.
    from sim.ik.limits import arm_soft_limits

    right = arm_soft_limits("right")
    left = arm_soft_limits("left")
    agreements: list[JointLimitAgreement] = []
    for index in range(ARM_JOINT_COUNT):
        sign = float(ARM_MIRROR_SIGNS[index])
        right_iv = (right[index].lower_rad.value, right[index].upper_rad.value)
        left_iv = (left[index].lower_rad.value, left[index].upper_rad.value)
        expected = _mirror_interval(right_iv, sign)
        matches = bool(np.isclose(expected[0], left_iv[0]) and np.isclose(expected[1], left_iv[1]))
        agreements.append(JointLimitAgreement(index, sign, right_iv, left_iv, matches))
    return tuple(agreements)


@dataclass(frozen=True)
class GripperBugDivergence:
    """Evidence that the gripper mirror diverges from LeRobot's buggy left limit.

    Attributes:
        lerobot_left_upper_rad: Upper bound of LeRobot's left-gripper soft limit.
        mirrored_open_rad: Our mirror of a fully-open right gripper.
        opposes_bug: Whether our mirror opens the direction the buggy limit forbids.
    """

    lerobot_left_upper_rad: float
    mirrored_open_rad: float
    opposes_bug: bool


def gripper_mirror_opposes_lerobot_bug() -> GripperBugDivergence:
    """Show the gripper mirror opens left where LeRobot's mirrored-out limit forbids.

    LeRobot's left-gripper soft limit keeps both bounds non-positive (the FR-MAN-017
    mirror bug), so a left gripper clamped to it never opens. Our mirror of a fully-open
    right gripper (``-GRIPPER_OPEN_RAD``) is ``+GRIPPER_OPEN_RAD`` — the opposite sign —
    which is the applied-mirror the acceptance requires.

    Returns:
        (GripperBugDivergence) The two values and whether they diverge as expected.
    """
    # Lazy for the same reason as convention_matches_pinned_limits: keep the core light.
    from sim.ik.limits import soft_limits

    lerobot_left_upper = soft_limits("left")[ARM_JOINT_COUNT].upper_rad.value
    mirrored_open = mirror_gripper(-GRIPPER_OPEN_RAD)
    opposes = bool(mirrored_open > 0.0 >= lerobot_left_upper)
    return GripperBugDivergence(lerobot_left_upper, mirrored_open, opposes)
