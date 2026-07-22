"""Shared trajectory fixtures for the WP-2D-06 tests."""

from __future__ import annotations

from backend.replay.waypoint import InterpolationMethod, ReplayWaypoint, TrajectorySpec

# A gentle right-arm sequence near home: within every soft limit and clear of collision at the
# default 50 Hz x 2 s timing. Three waypoints so dwell and gripper sequencing are exercised.
CLEAR_START = (0.0, 0.2, 0.0, 0.5, 0.0, 0.0, 0.0)
CLEAR_MID = (0.1, 0.3, 0.1, 0.6, 0.0, 0.0, 0.0)

# A right-arm end pose that self-collides part way along the sweep from CLEAR_START, the other
# arm held at home. The first violating sample lands mid-trajectory (index 24 of 101), so it
# exercises the "first violating waypoint index" report rather than an index-zero start clash.
SELF_COLLISION_END = (1.011, 0.041, -0.548, 0.076, 0.982, 0.58, 1.368)
SELF_COLLISION_FIRST_INDEX = 24


def clear_sequence(method: InterpolationMethod = InterpolationMethod.LINEAR) -> TrajectorySpec:
    """Return a three-waypoint, collision-free right-arm sequence with dwell and gripper.

    Args:
        method: The interpolation profile.

    Returns:
        (TrajectorySpec) The clear sequence.
    """
    return TrajectorySpec(
        waypoints=(
            ReplayWaypoint("right", CLEAR_START, gripper=-0.2, dwell_s=0.1, name="a"),
            ReplayWaypoint("right", CLEAR_MID, gripper=-0.4, name="b"),
            ReplayWaypoint("right", CLEAR_START, gripper=-0.2, dwell_s=0.2, name="c"),
        ),
        method=method,
    )


def two_point(
    start: tuple[float, ...],
    end: tuple[float, ...],
    method: InterpolationMethod = InterpolationMethod.LINEAR,
    velocity_scale: float = 1.0,
    other_arm_hold: tuple[float, ...] = (0.0,) * 7,
) -> TrajectorySpec:
    """Return a two-waypoint right-arm spec from start to end.

    Args:
        start: The start arm configuration, seven joints.
        end: The end arm configuration, seven joints.
        method: The interpolation profile.
        velocity_scale: The velocity scale.
        other_arm_hold: The stationary arm's held configuration.

    Returns:
        (TrajectorySpec) The two-point spec.
    """
    return TrajectorySpec(
        waypoints=(
            ReplayWaypoint("right", start, gripper=0.0),
            ReplayWaypoint("right", end, gripper=0.0),
        ),
        method=method,
        velocity_scale=velocity_scale,
        other_arm_hold=other_arm_hold,
    )
