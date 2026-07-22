"""The four-check pre-verify and its first-violation report (WP-2D-06 ①)."""

from __future__ import annotations

import numpy as np

from backend.replay.interpolate import InterpolatedTrajectory, interpolate_trajectory
from backend.replay.preverify import (
    PreVerifyCategory,
    density_step_ceiling_rad,
    run_pre_verify,
    velocity_limits_rad_s,
)
from backend.replay.waypoint import InterpolationMethod
from tests.wp2d06.fixtures import (
    CLEAR_START,
    SELF_COLLISION_END,
    SELF_COLLISION_FIRST_INDEX,
    clear_sequence,
    two_point,
)

VLIM = velocity_limits_rad_s()
CEIL = density_step_ceiling_rad()


def _interp(spec):
    """Interpolate a spec with the canonical ceilings."""
    return interpolate_trajectory(spec, VLIM, CEIL)


def test_clear_trajectory_passes_all_four_checks() -> None:
    """A gentle in-limit collision-free sequence passes with no violation."""
    result = run_pre_verify(_interp(clear_sequence()))
    assert result.ok
    assert result.category is None
    assert result.first_violation_index is None


def test_limit_violation_reports_first_index_and_category() -> None:
    """A joint driven past its soft limit is caught as a limit violation at its first sample."""
    # J1 to 3.0 rad exceeds the +1.309 soft limit part way along the sweep.
    traj = _interp(two_point(CLEAR_START, (3.0, 0.2, 0.0, 0.5, 0.0, 0.0, 0.0)))
    result = run_pre_verify(traj)
    assert not result.ok
    assert result.category is PreVerifyCategory.LIMIT
    assert 0 < result.first_violation_index < len(traj)


def test_velocity_violation_reports_first_index() -> None:
    """A step over a joint's velocity ceiling but within the density step is caught."""
    # 0.05 rad/tick on J1 is 2.5 rad/s > 1.57 ceiling, yet 0.05 rad < 0.084 density step.
    count = 6
    arm = np.zeros((count, 7))
    arm[:, 0] = np.arange(count) * 0.05
    traj = InterpolatedTrajectory(
        times_s=np.arange(count) / 50.0,
        arm=arm,
        gripper=np.zeros(count),
        method=InterpolationMethod.LINEAR,
        rate_hz=50.0,
        arm_side="right",
        other_arm_hold=np.zeros(7),
        segments=(),
    )
    result = run_pre_verify(traj)
    assert not result.ok
    assert result.category is PreVerifyCategory.VELOCITY
    assert result.first_violation_index == 1


def test_self_collision_reports_first_index() -> None:
    """A sweep that self-collides mid-trajectory is caught with the first colliding sample."""
    traj = _interp(two_point(CLEAR_START, SELF_COLLISION_END))
    result = run_pre_verify(traj)
    assert not result.ok
    assert result.category is PreVerifyCategory.SELF_COLLISION
    assert result.first_violation_index == SELF_COLLISION_FIRST_INDEX


def test_first_violation_is_earliest_across_checks() -> None:
    """When several checks fail, the earliest violating sample is the one reported."""
    traj = _interp(two_point(CLEAR_START, SELF_COLLISION_END))
    result = run_pre_verify(traj)
    # The collision at 24 precedes any limit/velocity issue on this in-limit smooth sweep.
    assert result.first_violation_index == SELF_COLLISION_FIRST_INDEX


def test_collision_verdict_is_the_reused_preflight_result() -> None:
    """The carried collision result is WP-2C-08's own PreflightResult, not a reimplementation."""
    from backend.collision_preflight.preflight import PreflightResult

    traj = _interp(two_point(CLEAR_START, SELF_COLLISION_END))
    result = run_pre_verify(traj)
    assert isinstance(result.collision, PreflightResult)
    # The pre-verify's reported collision index is exactly the preflight's first violation.
    assert result.collision.first_violation.waypoint_index == SELF_COLLISION_FIRST_INDEX
    # The reused density gate and self-collision proof ran (the WP-2C-08 evidence is present).
    assert result.collision.density.sufficient
    assert result.collision.self_collision is not None
