"""The left-gripper sign-mirror validator (FR-INF-070, the load-bearing check).

In a bimanual configuration the two grippers face each other, so the left gripper's
limit must be the SIGN-MIRROR of the right's, not an identical copy. The right pinch
closes over `(-65, 0)` degrees; its mirror is `(0, +65)`, because mirroring a bound
`(lo, hi)` negates and swaps it: `(-hi, -lo)`. If the left gripper carries the right's
`(-65, 0)` verbatim, its open direction (positive) is silently clipped to 0 — the
gripper never opens, yet no error fires.

That silent non-open is the reason this validator exists: it is a WRONG SUCCESS, not
a failure. The rollout runs, the success rate is merely low, and 4C's failure
taxonomy misreads it as a grasp failure rather than a limit bug. So an equality where
a mirror was required is a refusal, checked before the policy loads.
"""

from __future__ import annotations

from dataclasses import dataclass

# The follower limit-dict key for the gripper driver joint (MOTOR_ORDER / LeRobot).
GRIPPER_KEY = "gripper"

# Sign-mirror comparison tolerance in degrees; a real mirror is exact, this only
# absorbs float representation of the negated bounds.
MIRROR_TOLERANCE_DEG = 1e-6


def sign_mirror(limit: tuple[float, float]) -> tuple[float, float]:
    """Return the sign-mirror of a `(lower, upper)` bound: negate and swap.

    Args:
        limit: A `(lower, upper)` bound.

    Returns:
        (tuple[float, float]) `(-upper, -lower)` — the mirrored bound.
    """
    lower, upper = limit
    return (-upper, -lower)


@dataclass(frozen=True)
class GripperMirrorVerdict:
    """The result of one left-vs-right gripper mirror check.

    Attributes:
        ok: True when the left gripper equals the sign-mirror of the right.
        left: The observed left gripper limit (degrees).
        right: The observed right gripper limit (degrees).
        expected_left: The sign-mirror of the right the left should have equalled.
    """

    ok: bool
    left: tuple[float, float]
    right: tuple[float, float]
    expected_left: tuple[float, float]

    def detail(self) -> str:
        """Return the operator-facing sentence for a failed mirror."""
        return (
            f"left gripper {self.left} is not the sign-mirror of right {self.right}; "
            f"expected {self.expected_left}. An identical copy silently clips left-open "
            "(FR-INF-070)"
        )


def check_gripper_mirror(
    left_gripper: tuple[float, float],
    right_gripper: tuple[float, float],
    tolerance_deg: float = MIRROR_TOLERANCE_DEG,
) -> GripperMirrorVerdict:
    """Check that the left gripper limit is the sign-mirror of the right.

    Args:
        left_gripper: The left gripper `(lo, hi)` limit (degrees).
        right_gripper: The right gripper `(lo, hi)` limit (degrees).
        tolerance_deg: Absolute degree tolerance for the comparison.

    Returns:
        (GripperMirrorVerdict) Whether the mirror holds, and the values compared.
    """
    expected = sign_mirror(right_gripper)
    ok = (
        abs(left_gripper[0] - expected[0]) <= tolerance_deg
        and abs(left_gripper[1] - expected[1]) <= tolerance_deg
    )
    return GripperMirrorVerdict(
        ok=ok, left=left_gripper, right=right_gripper, expected_left=expected
    )


def check_gripper_mirror_from_limits(
    left_joint_limits: dict[str, tuple[float, float]],
    right_joint_limits: dict[str, tuple[float, float]],
    tolerance_deg: float = MIRROR_TOLERANCE_DEG,
) -> GripperMirrorVerdict:
    """Check the gripper mirror from two per-side `joint_limits` dicts.

    Args:
        left_joint_limits: The left arm's `motor_key -> (lo, hi)` limits (degrees).
        right_joint_limits: The right arm's limits (degrees).
        tolerance_deg: Absolute degree tolerance.

    Returns:
        (GripperMirrorVerdict) The gripper mirror verdict.
    """
    return check_gripper_mirror(
        left_joint_limits[GRIPPER_KEY], right_joint_limits[GRIPPER_KEY], tolerance_deg
    )
