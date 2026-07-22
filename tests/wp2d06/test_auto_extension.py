"""Velocity-scale duration auto-extension: velocity AND step-delta met at once (WP-2D-06 ②)."""

from __future__ import annotations

import numpy as np

from backend.replay.interpolate import interpolate_trajectory
from backend.replay.preverify import (
    density_step_ceiling_rad,
    run_pre_verify,
    velocity_limits_rad_s,
)
from backend.replay.waypoint import InterpolationMethod, ReplayWaypoint, TrajectorySpec
from tests.wp2d06.fixtures import clear_sequence, two_point

VLIM = velocity_limits_rad_s()
CEIL = density_step_ceiling_rad()


def _measured_peak_velocity(traj) -> np.ndarray:
    """Return the max finite-difference velocity per joint over a trajectory."""
    full = np.column_stack([traj.arm, traj.gripper])
    return np.max(np.abs(np.diff(full, axis=0)) * traj.rate_hz, axis=0)


def _measured_max_arm_step(traj) -> float:
    """Return the largest per-step arm-joint displacement over a trajectory."""
    return float(np.max(np.abs(np.diff(traj.arm, axis=0))))


def test_velocity_scale_extends_duration() -> None:
    """A smaller velocity scale extends the planned segment duration."""
    start = (0.0, 0.2, -1.0, 0.5, 0.0, 0.0, 0.0)
    end = (0.0, 0.2, 1.0, 0.5, 0.0, 0.0, 0.0)
    full = interpolate_trajectory(two_point(start, end, velocity_scale=1.0), VLIM, CEIL)
    slow = interpolate_trajectory(two_point(start, end, velocity_scale=0.1), VLIM, CEIL)
    assert slow.segments[0].planned_duration_s > full.segments[0].planned_duration_s
    assert slow.segments[0].velocity_extended


def test_extension_satisfies_velocity_and_step_simultaneously() -> None:
    """After a scale-driven extension both the velocity and the density step hold at once."""
    start = (0.0, 0.2, -1.0, 0.5, 0.0, 0.0, 0.0)
    end = (0.0, 0.2, 1.0, 0.5, 0.0, 0.0, 0.0)
    scale = 0.1
    traj = interpolate_trajectory(two_point(start, end, velocity_scale=scale), VLIM, CEIL)
    scaled_limits = scale * VLIM
    assert np.all(_measured_peak_velocity(traj) <= scaled_limits + 1e-9)
    assert _measured_max_arm_step(traj) < CEIL
    assert run_pre_verify(traj).ok


def test_wrist_move_extends_on_density_even_at_full_scale() -> None:
    """A fast wrist move under a short requested duration extends to meet the density step."""
    # A short requested duration makes the density step the binding floor for the wrist move.
    spec = TrajectorySpec(
        waypoints=(
            ReplayWaypoint("right", (0.0, 0.2, 0.0, 0.5, 0.0, 0.0, 0.0), gripper=0.0),
            ReplayWaypoint("right", (0.0, 0.2, 0.0, 0.5, 1.0, 0.0, 0.0), gripper=0.0),
        ),
        segment_duration_s=0.2,
    )
    traj = interpolate_trajectory(spec, VLIM, CEIL)
    assert traj.segments[0].density_extended
    assert traj.segments[0].planned_duration_s > 0.2
    assert _measured_max_arm_step(traj) < CEIL
    # At the un-extended 0.2 s the step would have exceeded the ceiling, proving the extension
    # was necessary: 1.0 rad over 0.2 s at 50 Hz is 0.1 rad/step > 0.084 rad ceiling.
    assert CEIL < (1.0 / (0.2 * 50.0))


def test_smooth_profiles_extend_more_than_linear() -> None:
    """A full J1 sweep extends by the profile peak factor: quintic > cubic > linear."""
    start = (-1.3, 0.2, 0.0, 0.5, 0.0, 0.0, 0.0)
    end = (1.3, 0.2, 0.0, 0.5, 0.0, 0.0, 0.0)
    durations = {}
    for method in InterpolationMethod:
        traj = interpolate_trajectory(two_point(start, end, method=method), VLIM, CEIL)
        durations[method] = traj.segments[0].planned_duration_s
    assert durations[InterpolationMethod.LINEAR] < durations[InterpolationMethod.CUBIC]
    assert durations[InterpolationMethod.CUBIC] < durations[InterpolationMethod.QUINTIC]


def test_held_dwell_samples_have_zero_velocity() -> None:
    """Dwell holds contribute zero velocity, so they never trip the velocity check."""
    traj = interpolate_trajectory(clear_sequence(), VLIM, CEIL)
    # The first five samples after the start are the 0.1 s dwell hold: zero displacement.
    dwell_steps = np.abs(np.diff(traj.arm[:6], axis=0))
    assert np.all(dwell_steps == 0.0)
