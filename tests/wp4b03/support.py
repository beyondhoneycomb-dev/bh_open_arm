"""Fixture builders for the WP-4B-03 load-preflight acceptance tests.

These construct the checkpoint and robot profiles each gate needs without pulling the
robot stack in. The gripper-limit dicts model the two states the mirror check
separates: the LeRobot soft default (left and right both `(-65, 0)`, the bug) and the
sign-mirror-correct pair.
"""

from __future__ import annotations

from backend.inference.load_preflight import CheckpointProfile, RobotProfile

# The right gripper's canonical pinch limit (degrees); its correct left mirror is
# (0, +65). The LeRobot soft default copies the right's onto the left verbatim.
_RIGHT_GRIPPER = (-65.0, 0.0)
_LEFT_GRIPPER_CORRECT = (0.0, 65.0)


def gripper_bug_limits() -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    """Return `(left, right)` per-arm limits where left copies right's `(-65, 0)` gripper.

    This is the FR-INF-070 failure: left-open is silently clipped.
    """
    right = {"gripper": _RIGHT_GRIPPER}
    left = {"gripper": _RIGHT_GRIPPER}
    return left, right


def gripper_mirror_limits() -> tuple[
    dict[str, tuple[float, float]], dict[str, tuple[float, float]]
]:
    """Return `(left, right)` per-arm limits whose grippers are correct sign-mirrors."""
    right = {"gripper": _RIGHT_GRIPPER}
    left = {"gripper": _LEFT_GRIPPER_CORRECT}
    return left, right


def matching_checkpoint(robot: RobotProfile, policy_id: str | None = None) -> CheckpointProfile:
    """Return a checkpoint whose widths match a robot profile (a loadable pairing)."""
    return CheckpointProfile(
        input_dim=robot.observation_dim(),
        output_dim=robot.action_dim(),
        policy_id=policy_id,
    )
