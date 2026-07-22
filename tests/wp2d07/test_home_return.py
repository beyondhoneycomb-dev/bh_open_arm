"""Acceptance ① + ②: the target is shown before execution, and a failed pre-verify halts.

① every plan carries the active home name and its target posture (joints + EE pose) before
anything runs; ② a colliding start makes the pre-verify fail, and the plan then does not
auto-run — it is non-executable, demands a waypoint, and refuses to hand back a trajectory.
A benign intermediate waypoint that clears is executable, proving the detour is re-verified.
"""

from __future__ import annotations

import math

import pytest

from backend.home.homereturn import HomeReturn, HomeReturnBlockedError
from tests.wp2d07.conftest import BENIGN_WAYPOINT, COLLIDING_START, SAFE_START


def test_preview_shows_active_home_and_target_before_execution(home: HomeReturn) -> None:
    """① The active home name and target posture are available before any execution."""
    preview = home.preview()
    assert preview.profile_name == "default"
    assert preview.j4_angle_rad == pytest.approx(math.pi / 2)
    assert preview.q_urdf == (0.0, 0.0, 0.0, pytest.approx(math.pi / 2), 0.0, 0.0, 0.0, 0.0)
    assert len(preview.limit_margins) == 16


def test_preview_ee_pose_matches_committed_home(home: HomeReturn) -> None:
    """① The shown target EE pose is the committed home EE (04 §3.6): right (0.401,-0.1535,1.12)."""
    preview = home.preview()
    assert preview.ee_pose_right[:3] == pytest.approx((0.401, -0.1535, 1.12), abs=1e-3)
    assert preview.ee_pose_right[3:] == pytest.approx((0.7071, 0.0, -0.7071, 0.0), abs=1e-3)
    assert preview.ee_pose_left[:3] == pytest.approx((0.401, 0.1535, 1.12), abs=1e-3)


def test_safe_start_pre_verifies_and_is_executable(home: HomeReturn) -> None:
    """A start whose path to home clears every check is executable with real trajectories."""
    plan = home.plan_return(SAFE_START)
    assert plan.executable is True
    assert plan.requires_waypoint is False
    assert all(leg.ok for leg in plan.legs)
    right_traj, left_traj = plan.executable_trajectory()
    assert len(right_traj) > 1
    assert len(left_traj) > 1


def test_failed_pre_verify_does_not_auto_run_and_requires_waypoint(home: HomeReturn) -> None:
    """② A colliding start fails pre-verify: the plan does not auto-run and demands a waypoint."""
    plan = home.plan_return(COLLIDING_START)
    assert plan.executable is False
    assert plan.requires_waypoint is True
    assert not all(leg.ok for leg in plan.legs)
    assert "waypoint" in plan.reason
    # The preview is still shown even though the pre-verify failed (① holds regardless).
    assert plan.preview.profile_name == "default"


def test_colliding_start_fails_on_the_reused_collision_check(home: HomeReturn) -> None:
    """② The colliding start fails specifically on the reused WP-2C-08 self-collision check."""
    plan = home.plan_return(COLLIDING_START)
    right_leg = next(leg for leg in plan.legs if leg.side == "right")
    assert right_leg.ok is False
    assert right_leg.verdict.category is not None
    assert right_leg.verdict.category.value == "self_collision"
    assert right_leg.verdict.first_violation_index is not None


def test_blocked_plan_refuses_to_hand_back_a_trajectory(home: HomeReturn) -> None:
    """② A blocked plan raises rather than returning the trajectory it would have run."""
    plan = home.plan_return(COLLIDING_START)
    with pytest.raises(HomeReturnBlockedError):
        plan.executable_trajectory()


def test_waypoint_that_clears_makes_the_plan_executable(home: HomeReturn) -> None:
    """② A benign intermediate waypoint whose whole detour clears is executable."""
    plan = home.plan_return(SAFE_START, waypoints=[BENIGN_WAYPOINT])
    assert plan.executable is True
    assert all(leg.ok for leg in plan.legs)
    right_traj, left_traj = plan.executable_trajectory()
    assert len(right_traj) > 1


def test_plan_as_record_is_complete(home: HomeReturn) -> None:
    """The plan renders preview, both legs, and disposition for evidence."""
    record = home.plan_return(SAFE_START).as_record()
    assert set(record) == {"preview", "legs", "executable", "requires_waypoint", "reason"}
    assert record["preview"]["profile_name"] == "default"
    assert len(record["legs"]) == 2
    assert {leg["side"] for leg in record["legs"]} == {"right", "left"}


def test_reuses_wp2d01_kinematic_frames() -> None:
    """The EE preview is FK over the reused WP-2D-01 KinematicFrames, not a second kinematic."""
    from backend.cartesian_jog.frames import KinematicFrames as JogFrames
    from backend.home import homereturn

    assert homereturn.KinematicFrames is JogFrames
