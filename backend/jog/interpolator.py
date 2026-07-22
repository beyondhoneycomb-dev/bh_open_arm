"""The `np.linspace` jog interpolator — one command becomes a trajectory (`WP-2A-01`).

LeRobot has no interpolator, so a single jog step sent as one `send_action` would
be a step discontinuity at the joint (`04` FR-MAN-010, `[신규구현]`). This module is
the interpolator the spec says we must build: it turns a single step or a
continuous hold into a time-stamped sequence of position requests, spaced by
`np.linspace`, that the producer publishes one waypoint at a time.

Why a *sequence* and not one request: the scheduler mailbox is latest-wins with a
single slot, so publishing a whole trajectory at once would leave only its last
waypoint. The trajectory is therefore paired with per-waypoint monotonic times, and
a driver publishes each waypoint at its time while the scheduler ticks between them
— which is exactly what makes "emitted frames = hz × duration" the observable form
of an interpolated step (`02b` WP-2A-01 acceptance ②).

This module never touches CAN or the scheduler: it plans values in `Deg`, and the
planning functions are pure — the same inputs yield the same trajectory, so a test
can assert frame counts and endpoints without a clock or a bus.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from backend.jog.addressing import JogAddress, JogDirection, validate_step_size
from backend.jog.config import DEFAULT_INTERPOLATION_HZ, DEFAULT_STEP_DURATION_SEC
from contracts.action import RequestedPositionAction
from contracts.units import Deg, DegPerSec


@dataclass(frozen=True)
class JogWaypoint:
    """One interpolated position request and the monotonic time to publish it at.

    Attributes:
        request: The 16-dim bimanual position request at this waypoint (CTR-ACT).
        at: Monotonic time, in seconds, at which this waypoint should be published;
            read on the same clock the scheduler ticks against, never wall time.
    """

    request: RequestedPositionAction
    at: float


@dataclass(frozen=True)
class JogTrajectory:
    """A time-ordered sequence of interpolated waypoints for one jog action.

    Attributes:
        waypoints: The waypoints in publish order; the first re-commands the origin
            and the last commands the target, so the length is the emitted frame
            count `round(hz * duration)`.
    """

    waypoints: tuple[JogWaypoint, ...]

    def __len__(self) -> int:
        """Return the number of waypoints (the emitted frame count)."""
        return len(self.waypoints)


def frame_count(hz: float, duration: float) -> int:
    """Number of interpolated frames a jog of `duration` at `hz` emits.

    Args:
        hz: Interpolation cadence, waypoints per second.
        duration: Jog duration, seconds.

    Returns:
        (int) `round(hz * duration)`, at least one frame.

    Raises:
        ValueError: If `hz` or `duration` is not positive.
    """
    if hz <= 0.0:
        raise ValueError(f"hz must be positive, got {hz}")
    if duration <= 0.0:
        raise ValueError(f"duration must be positive, got {duration}")
    return max(1, round(hz * duration))


def _as_array(request: RequestedPositionAction) -> npt.NDArray[np.float64]:
    """Read a position request into a float64 array of degree magnitudes."""
    return np.asarray([angle.value for angle in request.values], dtype=np.float64)


def _as_request(row: npt.NDArray[np.float64]) -> RequestedPositionAction:
    """Wrap one interpolated row back into a `Deg`-tagged position request."""
    return RequestedPositionAction(values=tuple(Deg(float(value)) for value in row))


def _linspace_trajectory(
    origin: npt.NDArray[np.float64],
    target: npt.NDArray[np.float64],
    start_mono: float,
    hz: float,
    frames: int,
) -> JogTrajectory:
    """Build the interpolated trajectory from origin to target over `frames` waypoints.

    `np.linspace` spans both endpoints, so the first waypoint re-commands the origin
    and the last commands the target; every joint whose origin equals its target
    stays constant, which is how a single-joint jog leaves the other fifteen joints
    untouched.

    Args:
        origin: The starting 16-dim pose, degrees.
        target: The ending 16-dim pose, degrees.
        start_mono: Monotonic time of the first waypoint, seconds.
        hz: Interpolation cadence, waypoints per second.
        frames: Number of waypoints to emit.

    Returns:
        (JogTrajectory) The waypoints, evenly spaced in value and in time.
    """
    grid = np.linspace(origin, target, num=frames, dtype=np.float64)
    interval = 1.0 / hz
    return JogTrajectory(
        tuple(
            JogWaypoint(request=_as_request(grid[frame]), at=start_mono + frame * interval)
            for frame in range(frames)
        )
    )


def plan_step_trajectory(
    origin: RequestedPositionAction,
    address: JogAddress,
    direction: JogDirection,
    step: Deg,
    start_mono: float,
    hz: float = DEFAULT_INTERPOLATION_HZ,
    duration: float = DEFAULT_STEP_DURATION_SEC,
) -> JogTrajectory:
    """Interpolate one step of the addressed joint into a trajectory (FR-MAN-010).

    The addressed joint moves by `direction * step`; every other joint holds. The
    result has `round(hz * duration)` waypoints, so one step is emitted as a
    trajectory, never a single discontinuous command.

    Args:
        origin: The current 16-dim pose the step departs from, degrees.
        address: Which arm and joint to jog.
        direction: `+` or `−` sense of the step.
        step: Step magnitude; must be one of the offered step sizes.
        start_mono: Monotonic time of the first waypoint, seconds.
        hz: Interpolation cadence, waypoints per second.
        duration: Step duration, seconds.

    Returns:
        (JogTrajectory) The interpolated waypoints for this one step.

    Raises:
        ValueError: If `step` is off-vocabulary, or `hz`/`duration` is non-positive.
    """
    validate_step_size(step)
    frames = frame_count(hz, duration)
    origin_array = _as_array(origin)
    target_array = origin_array.copy()
    target_array[address.index] += direction.value * step.value
    return _linspace_trajectory(origin_array, target_array, start_mono, hz, frames)


def plan_continuous_trajectory(
    origin: RequestedPositionAction,
    address: JogAddress,
    direction: JogDirection,
    velocity: DegPerSec,
    start_mono: float,
    hz: float = DEFAULT_INTERPOLATION_HZ,
    duration: float = DEFAULT_STEP_DURATION_SEC,
) -> JogTrajectory:
    """Interpolate a continuous (hold-to-move) jog for the held duration (FR-MAN-009).

    Continuous mode moves the addressed joint at `velocity` while the operator holds;
    releasing simply stops the driver publishing further waypoints, and the scheduler
    then holds the last accepted position (the Cat-2 hold is the scheduler's, not
    this producer's). The commanded rate is an input here — bounding it against the
    active velocity limit is `WP-2A-04`'s `VelocityLimiter`, deliberately not
    re-implemented in the producer.

    Args:
        origin: The current 16-dim pose the jog departs from, degrees.
        address: Which arm and joint to jog.
        direction: `+` or `−` sense of the motion.
        velocity: Commanded joint rate, degrees per second.
        start_mono: Monotonic time of the first waypoint, seconds.
        hz: Interpolation cadence, waypoints per second.
        duration: How long the hold is sustained, seconds.

    Returns:
        (JogTrajectory) The interpolated waypoints for the held interval.

    Raises:
        ValueError: If `hz` or `duration` is non-positive.
    """
    frames = frame_count(hz, duration)
    origin_array = _as_array(origin)
    target_array = origin_array.copy()
    target_array[address.index] += direction.value * velocity.value * duration
    return _linspace_trajectory(origin_array, target_array, start_mono, hz, frames)
