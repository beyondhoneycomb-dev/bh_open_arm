"""Interpolation profiles, dwell, gripper, and multi-point sequencing (WP-2D-06)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.replay.constants import DEFAULT_RATE_HZ
from backend.replay.interpolate import ease, interpolate_trajectory
from backend.replay.preverify import density_step_ceiling_rad, velocity_limits_rad_s
from backend.replay.waypoint import (
    InterpolationMethod,
    ReplayWaypoint,
    TrajectorySpec,
    dwell_sample_count,
)
from tests.wp2d06.fixtures import CLEAR_MID, CLEAR_START, clear_sequence

VLIM = velocity_limits_rad_s()
CEIL = density_step_ceiling_rad()


def _interp(spec: TrajectorySpec):
    """Interpolate a spec with the canonical ceilings."""
    return interpolate_trajectory(spec, VLIM, CEIL)


@pytest.mark.parametrize("method", list(InterpolationMethod))
def test_endpoints_are_exact(method: InterpolationMethod) -> None:
    """Every profile hits the two waypoints exactly at the segment ends."""
    traj = _interp(clear_sequence(method))
    np.testing.assert_allclose(traj.arm[0], CLEAR_START, atol=1e-12)
    # The mid waypoint is reached at the boundary between the two segments.
    boundary = traj.segments[0].n_steps + dwell_sample_count(0.1, DEFAULT_RATE_HZ)
    np.testing.assert_allclose(traj.arm[boundary], CLEAR_MID, atol=1e-9)


def test_ease_boundary_values() -> None:
    """Each easing maps 0->0 and 1->1, and the smooth profiles have zero endpoint slope."""
    u = np.array([0.0, 1.0])
    for method in InterpolationMethod:
        np.testing.assert_allclose(ease(method, u), [0.0, 1.0], atol=1e-12)
    # Cubic/quintic derivative at the endpoints is zero: a tiny step from 0 barely moves.
    small = np.array([1e-4])
    assert ease(InterpolationMethod.CUBIC, small)[0] < 1e-4
    assert ease(InterpolationMethod.QUINTIC, small)[0] < 1e-4
    # Linear moves proportionally at the endpoint.
    assert ease(InterpolationMethod.LINEAR, small)[0] == pytest.approx(1e-4)


def test_times_are_monotonic_uniform_grid() -> None:
    """Sample times increase on a uniform 1/rate grid across the whole trajectory."""
    traj = _interp(clear_sequence())
    diffs = np.diff(traj.times_s)
    np.testing.assert_allclose(diffs, 1.0 / DEFAULT_RATE_HZ, atol=1e-12)


def test_dwell_inserts_held_samples() -> None:
    """A dwell inserts held samples equal to round(dwell_s * rate) at the waypoint config."""
    traj = _interp(clear_sequence())
    # The first waypoint dwells 0.1 s at 50 Hz -> five held samples after the start sample.
    held = dwell_sample_count(0.1, DEFAULT_RATE_HZ)
    assert held == 5
    for index in range(1, held + 1):
        np.testing.assert_allclose(traj.arm[index], CLEAR_START, atol=1e-12)


def test_gripper_interpolates_between_waypoints() -> None:
    """The gripper moves monotonically from one waypoint value toward the next."""
    spec = TrajectorySpec(
        waypoints=(
            ReplayWaypoint("right", CLEAR_START, gripper=-0.2),
            ReplayWaypoint("right", CLEAR_START, gripper=-0.8),
        )
    )
    traj = _interp(spec)
    assert traj.gripper[0] == pytest.approx(-0.2)
    assert traj.gripper[-1] == pytest.approx(-0.8)
    assert np.all(np.diff(traj.gripper) <= 1e-12)


def test_multi_point_sequence_spans_all_waypoints() -> None:
    """A three-waypoint sequence produces two timed segments in order."""
    traj = _interp(clear_sequence())
    assert len(traj.segments) == 2
    assert [segment.index for segment in traj.segments] == [0, 1]


def test_spec_rejects_single_waypoint() -> None:
    """A spec with fewer than two waypoints is rejected at construction."""
    with pytest.raises(ValueError, match="at least two waypoints"):
        TrajectorySpec(waypoints=(ReplayWaypoint("right", CLEAR_START, gripper=0.0),))


def test_spec_rejects_mixed_sides() -> None:
    """A spec mixing arm sides is rejected: a trajectory is single-arm."""
    with pytest.raises(ValueError, match="one arm side"):
        TrajectorySpec(
            waypoints=(
                ReplayWaypoint("right", CLEAR_START, gripper=0.0),
                ReplayWaypoint("left", CLEAR_START, gripper=0.0),
            )
        )


def test_waypoint_rejects_wrong_joint_count() -> None:
    """A waypoint whose arm vector is not seven joints is rejected."""
    with pytest.raises(ValueError, match="7 joints"):
        ReplayWaypoint("right", (0.0, 0.0, 0.0), gripper=0.0)
