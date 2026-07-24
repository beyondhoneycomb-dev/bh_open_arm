"""CG-4B-03b — a left gripper equal to the right's (-65, 0) is refused (mirror check).

FR-INF-070: in a bimanual configuration the left gripper limit must be the sign-mirror
of the right's, `(0, +65)`, not an identical copy. A left gripper carrying the right's
`(-65, 0)` verbatim silently clips left-open — a WRONG SUCCESS 4C would misread as a
grasp failure — so the load is refused before the policy loads.

The real LeRobot soft defaults carry exactly this bug (both sides `(-65, 0)`), so this
also proves the check bites on the installed configuration, not only a synthetic one.
"""

from __future__ import annotations

from lerobot.robots.openarm_follower.config_openarm_follower import (
    LEFT_DEFAULT_JOINTS_LIMITS,
    RIGHT_DEFAULT_JOINTS_LIMITS,
)

from backend.inference.load_preflight import (
    LoadPreflight,
    RefusalCode,
    RobotProfile,
    check_gripper_mirror,
    check_gripper_mirror_from_limits,
    sign_mirror,
)
from tests.wp4b03.support import (
    gripper_bug_limits,
    gripper_mirror_limits,
    matching_checkpoint,
)


def test_left_equals_right_gripper_is_refused() -> None:
    """CG-4B-03b: left gripper == right's (-65, 0) -> load refused."""
    left, right = gripper_bug_limits()
    robot = RobotProfile.bimanual_profile(
        use_velocity_and_torque=True, left_joint_limits=left, right_joint_limits=right
    )
    checkpoint = matching_checkpoint(robot, policy_id="groot")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert not verdict.allowed
    assert any(r.code is RefusalCode.GRIPPER_MIRROR for r in verdict.refusals)


def test_correct_mirror_is_allowed() -> None:
    """The sign-mirror-correct pair (left (0, 65), right (-65, 0)) loads (not vacuous)."""
    left, right = gripper_mirror_limits()
    robot = RobotProfile.bimanual_profile(
        use_velocity_and_torque=True, left_joint_limits=left, right_joint_limits=right
    )
    checkpoint = matching_checkpoint(robot, policy_id="groot")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert verdict.allowed


def test_sign_mirror_negates_and_swaps() -> None:
    """The mirror of (-65, 0) is (0, 65): negate and swap the bounds."""
    assert sign_mirror((-65.0, 0.0)) == (0.0, 65.0)
    assert check_gripper_mirror((0.0, 65.0), (-65.0, 0.0)).ok
    assert not check_gripper_mirror((-65.0, 0.0), (-65.0, 0.0)).ok


def test_lerobot_soft_defaults_carry_the_bug() -> None:
    """The installed LeRobot soft defaults have left gripper == right gripper == (-65, 0)."""
    assert LEFT_DEFAULT_JOINTS_LIMITS["gripper"] == RIGHT_DEFAULT_JOINTS_LIMITS["gripper"]

    left = {"gripper": tuple(LEFT_DEFAULT_JOINTS_LIMITS["gripper"])}
    right = {"gripper": tuple(RIGHT_DEFAULT_JOINTS_LIMITS["gripper"])}
    verdict = check_gripper_mirror_from_limits(left, right)

    assert not verdict.ok
    assert verdict.expected_left == (0.0, 65.0)
