"""Consuming WP-2D-05 teaching points, and the reused zero-match replay gate (WP-2D-06)."""

from __future__ import annotations

import pytest

import backend.replay.teaching as teaching_module
from backend.calibration.schema import ZeroMethod
from backend.replay.replay import ReplayExecutor
from backend.replay.teaching import (
    ZeroMatchBlockedError,
    build_replay_from_points,
    waypoint_from_teaching_point,
)
from backend.teaching.point import TeachingPoint
from backend.teaching.zero_match import ZeroIdentity, evaluate_replay
from tests.wp2d06.fixtures import CLEAR_MID, CLEAR_START

ZERO_METHOD = ZeroMethod.LEROBOT_HANGING
ZEROED_AT = "2026-07-20T00:00:00+00:00"


def _point(name: str, q_arm: tuple[float, ...], gripper: float) -> TeachingPoint:
    """Build a right-arm teaching point with matching zero provenance."""
    return TeachingPoint(
        name=name,
        arm_side="right",
        q_urdf=[*q_arm, gripper],
        ee_pose=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        gain_profile="default",
        zero_method=ZERO_METHOD,
        zeroed_at=ZEROED_AT,
        q_lift=0.0,
        timestamp=ZEROED_AT,
    )


CURRENT_ZERO = ZeroIdentity(side="right", zero_method=ZERO_METHOD, zeroed_at=ZEROED_AT)


def test_waypoint_splits_q_urdf_into_arm_and_gripper() -> None:
    """The eight-wide q_urdf becomes seven arm joints and the gripper."""
    point = _point("a", CLEAR_START, gripper=-0.3)
    waypoint = waypoint_from_teaching_point(point, dwell_s=0.5)
    assert waypoint.q_arm == CLEAR_START
    assert waypoint.gripper == pytest.approx(-0.3)
    assert waypoint.arm_side == "right"
    assert waypoint.dwell_s == 0.5
    assert waypoint.name == "a"


def test_build_from_matched_points_returns_executor() -> None:
    """A zero-matched, collision-free teaching sequence builds a runnable executor."""
    points = [_point("a", CLEAR_START, -0.2), _point("b", CLEAR_MID, -0.4)]
    executor = build_replay_from_points(points, CURRENT_ZERO)
    assert isinstance(executor, ReplayExecutor)


def test_rezeroed_reference_blocks_replay() -> None:
    """A re-zero since teaching blocks the replay through the reused WP-2D-05 gate."""
    points = [_point("a", CLEAR_START, -0.2), _point("b", CLEAR_MID, -0.4)]
    rezeroed = ZeroIdentity(
        side="right", zero_method=ZERO_METHOD, zeroed_at="2026-07-21T00:00:00+00:00"
    )
    with pytest.raises(ZeroMatchBlockedError) as excinfo:
        build_replay_from_points(points, rezeroed)
    assert len(excinfo.value.verdicts) == 2
    assert "re-zeroed" in excinfo.value.verdicts[0].reason


def test_unzeroed_robot_blocks_replay() -> None:
    """A robot with no zero record blocks every taught point."""
    points = [_point("a", CLEAR_START, -0.2), _point("b", CLEAR_MID, -0.4)]
    unzeroed = ZeroIdentity(side="right", zero_method=ZERO_METHOD, zeroed_at=None)
    with pytest.raises(ZeroMatchBlockedError):
        build_replay_from_points(points, unzeroed)


def test_reuses_the_teaching_zero_match_gate() -> None:
    """The gate is backend.teaching.evaluate_replay, not a second zero-match rule."""
    assert teaching_module.evaluate_replay is evaluate_replay
