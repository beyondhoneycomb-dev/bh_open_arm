"""Waypoint interpolation with velocity-scale duration auto-extension (WP-2D-06 ①/②).

The interpolator turns a sparse `TrajectorySpec` into a dense, uniform-rate trajectory. Its
one non-obvious job is the auto-extension (`02b` WP-2D-06 ②): a segment's duration is
stretched until the peak joint velocity is under BOTH the (velocity-scaled) per-joint
velocity ceiling AND the per-step displacement is under the `WP-2C-08` density ceiling —
simultaneously, not one at a time. Both bounds reduce to a floor on the segment duration, and
the planned duration is the larger of the requested duration and those two floors.

The grid is uniform at `rate_hz` across the whole trajectory (dt = 1/rate), so a segment that
extends simply spends more ticks; the discrete finite-difference velocity between two ticks
never exceeds the profile's continuous peak, so satisfying the peak bound satisfies the
sampled trajectory the pre-verify actually walks. This module holds no physical constants: the
velocity ceilings and the density step ceiling are passed in from their single sources
(`backend.safety_bringup.velocity`, `WP-2C-08` geometry) by the caller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from backend.replay.constants import (
    CUBIC_PEAK_FACTOR,
    DENSITY_TARGET_FRACTION,
    LINEAR_PEAK_FACTOR,
    LINEAR_RESIDUAL_UI_NOTE,
    MIN_SAMPLES_PER_SEGMENT,
    QUINTIC_PEAK_FACTOR,
)
from backend.replay.waypoint import (
    InterpolationMethod,
    TrajectorySpec,
    dwell_sample_count,
)
from backend.safety_bringup.constants import ARM_JOINT_COUNT

_PEAK_FACTOR = {
    InterpolationMethod.LINEAR: LINEAR_PEAK_FACTOR,
    InterpolationMethod.CUBIC: CUBIC_PEAK_FACTOR,
    InterpolationMethod.QUINTIC: QUINTIC_PEAK_FACTOR,
}


def ease(method: InterpolationMethod, u: np.ndarray) -> np.ndarray:
    """Map a normalized parameter u in [0, 1] to eased progress s in [0, 1].

    Args:
        method: The interpolation profile.
        u: Normalized parameters, shape (N,), each in [0, 1].

    Returns:
        (np.ndarray) Eased progress, shape (N,). Linear is identity; cubic is the smoothstep
        3u^2-2u^3 (zero endpoint velocity); quintic is 10u^3-15u^4+6u^5 (zero endpoint
        velocity and acceleration).
    """
    if method is InterpolationMethod.LINEAR:
        return u
    if method is InterpolationMethod.CUBIC:
        return u * u * (3.0 - 2.0 * u)
    return u * u * u * (10.0 - 15.0 * u + 6.0 * u * u)


@dataclass(frozen=True)
class SegmentPlan:
    """How one waypoint-to-waypoint segment was timed (`02b` WP-2D-06 ②).

    Attributes:
        index: Zero-based segment index (segment i joins waypoint i to i+1).
        requested_duration_s: The planned per-segment duration before extension.
        planned_duration_s: The duration after extension for velocity and density.
        n_steps: The number of grid steps (samples added after the segment start).
        velocity_extended: True when the velocity ceiling forced the extension.
        density_extended: True when the density step ceiling forced the extension.
    """

    index: int
    requested_duration_s: float
    planned_duration_s: float
    n_steps: int
    velocity_extended: bool
    density_extended: bool

    @property
    def extended(self) -> bool:
        """Whether either ceiling extended this segment beyond the requested duration."""
        return self.velocity_extended or self.density_extended


@dataclass(frozen=True)
class InterpolatedTrajectory:
    """A dense, pre-verifiable trajectory produced from a `TrajectorySpec`.

    Attributes:
        times_s: Monotonic sample times, shape (N,), on a uniform 1/rate grid.
        arm: The moving arm's joint angles, shape (N, 7), radians.
        gripper: The gripper angle per sample, shape (N,), radians.
        method: The interpolation profile used.
        rate_hz: The grid rate.
        arm_side: `"right"` or `"left"`.
        other_arm_hold: The stationary arm's held configuration, shape (7,).
        segments: Per-segment timing, one entry per waypoint pair.
    """

    times_s: np.ndarray
    arm: np.ndarray
    gripper: np.ndarray
    method: InterpolationMethod
    rate_hz: float
    arm_side: str
    other_arm_hold: np.ndarray
    segments: tuple[SegmentPlan, ...]

    def __len__(self) -> int:
        """Return the number of samples in the trajectory."""
        return int(self.arm.shape[0])

    def residual_ui_note(self) -> str:
        """Return the residual-pollution UI note for a linear profile, else empty (④).

        Returns:
            (str) The `LINEAR_RESIDUAL_UI_NOTE` when the profile is linear, else "".
        """
        return LINEAR_RESIDUAL_UI_NOTE if self.method is InterpolationMethod.LINEAR else ""


def _segment_duration_s(
    start: np.ndarray,
    end: np.ndarray,
    peak_factor: float,
    rate_hz: float,
    requested_s: float,
    velocity_scale: float,
    velocity_limits: np.ndarray,
    density_step_ceiling: float,
) -> tuple[float, bool, bool]:
    """Return the extended segment duration and which ceiling forced the extension (②).

    Both the velocity ceiling and the density step ceiling reduce to a floor on the segment
    duration. Peak joint velocity is `peak_factor * |delta| / T`; requiring it under the
    scaled ceiling gives `T >= peak_factor * |delta| / (scale * limit)`. The largest per-step
    displacement is `peak_factor * |delta| / (rate * T)`; requiring it under the density
    target gives `T >= peak_factor * |delta| / (rate * target)`. The density bound covers the
    seven arm joints only — the gripper (finger) is held at zero in the collision model.

    Args:
        start: The segment's start configuration, shape (8,): seven arm joints then gripper.
        end: The segment's end configuration, shape (8,).
        peak_factor: The profile's peak-to-mean velocity ratio.
        rate_hz: The grid rate.
        requested_s: The requested duration before extension.
        velocity_scale: Fraction of the velocity ceiling the motion may use.
        velocity_limits: Per-joint velocity ceilings, shape (8,): seven arm then gripper.
        density_step_ceiling: The `WP-2C-08` per-step joint displacement ceiling, radians.

    Returns:
        (float) The planned duration, the larger of the requested duration and both floors.
        velocity_extended (bool) whether the velocity floor exceeded the requested duration.
        density_extended (bool) whether the density floor exceeded the requested duration.
    """
    delta = np.abs(end - start)
    scaled_limits = velocity_scale * velocity_limits

    t_velocity = 0.0
    for joint in range(delta.shape[0]):
        if delta[joint] > 0.0 and scaled_limits[joint] > 0.0:
            t_velocity = max(
                t_velocity, peak_factor * float(delta[joint]) / float(scaled_limits[joint])
            )

    step_target = density_step_ceiling * DENSITY_TARGET_FRACTION
    t_density = 0.0
    for joint in range(ARM_JOINT_COUNT):
        if delta[joint] > 0.0:
            t_density = max(t_density, peak_factor * float(delta[joint]) / (rate_hz * step_target))

    planned = max(requested_s, t_velocity, t_density)
    return planned, t_velocity > requested_s, t_density > requested_s


def interpolate_trajectory(
    spec: TrajectorySpec,
    velocity_limits: np.ndarray,
    density_step_ceiling: float,
) -> InterpolatedTrajectory:
    """Interpolate a spec into a dense trajectory, auto-extending each segment (①/②).

    Args:
        spec: The multi-point sequence and its interpolation settings.
        velocity_limits: Per-joint velocity ceilings, shape (8,): seven arm then gripper,
            from the single canonical source.
        density_step_ceiling: The `WP-2C-08` per-step joint displacement ceiling, radians.

    Returns:
        (InterpolatedTrajectory) The uniform-rate trajectory, dwell holds inserted at each
        waypoint, with per-segment timing recorded.
    """
    velocity_limits = np.asarray(velocity_limits, dtype=float)
    peak_factor = _PEAK_FACTOR[spec.method]
    dt = 1.0 / spec.rate_hz
    min_steps = MIN_SAMPLES_PER_SEGMENT - 1

    def waypoint_vec(index: int) -> np.ndarray:
        point = spec.waypoints[index]
        return np.concatenate([np.asarray(point.q_arm, dtype=float), [float(point.gripper)]])

    times: list[float] = [0.0]
    configs: list[np.ndarray] = [waypoint_vec(0)]
    segments: list[SegmentPlan] = []
    clock = 0.0

    def hold(config: np.ndarray, count: int) -> None:
        nonlocal clock
        for _ in range(count):
            clock += dt
            times.append(clock)
            configs.append(config)

    hold(waypoint_vec(0), dwell_sample_count(spec.waypoints[0].dwell_s, spec.rate_hz))

    for index in range(len(spec.waypoints) - 1):
        start = waypoint_vec(index)
        end = waypoint_vec(index + 1)
        planned, velocity_extended, density_extended = _segment_duration_s(
            start,
            end,
            peak_factor,
            spec.rate_hz,
            spec.segment_duration_s,
            spec.velocity_scale,
            velocity_limits,
            density_step_ceiling,
        )
        n_steps = max(min_steps, math.ceil(planned * spec.rate_hz))
        progress = ease(spec.method, np.linspace(0.0, 1.0, n_steps + 1))
        for step in range(1, n_steps + 1):
            clock += dt
            times.append(clock)
            configs.append(start + progress[step] * (end - start))
        segments.append(
            SegmentPlan(
                index=index,
                requested_duration_s=spec.segment_duration_s,
                planned_duration_s=n_steps * dt,
                n_steps=n_steps,
                velocity_extended=velocity_extended,
                density_extended=density_extended,
            )
        )
        hold(end, dwell_sample_count(spec.waypoints[index + 1].dwell_s, spec.rate_hz))

    stacked = np.asarray(configs, dtype=float)
    return InterpolatedTrajectory(
        times_s=np.asarray(times, dtype=float),
        arm=stacked[:, :ARM_JOINT_COUNT].copy(),
        gripper=stacked[:, ARM_JOINT_COUNT].copy(),
        method=spec.method,
        rate_hz=spec.rate_hz,
        arm_side=spec.arm_side,
        other_arm_hold=np.asarray(spec.other_arm_hold, dtype=float),
        segments=tuple(segments),
    )
