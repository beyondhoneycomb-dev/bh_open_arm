"""Consume WP-2D-05 teaching points into a replay (WP-2D-06 consumes WP-2D-05).

Replay's input is a teaching sequence, and the teaching schema and its zero-match gate are
`WP-2D-05` (`backend.teaching`), not this band. This module is the seam: it splits a
`TeachingPoint`'s `q_urdf[8]` into the seven arm joints and the gripper the interpolator
consumes, and it runs the reused zero-match gate (`evaluate_replay`) as a replay precondition —
a point taught against a zero reference the robot no longer holds is BLOCKED, so the same joint
angles are never replayed as a different physical pose (`02b` §4.2, FR-MAN-039/040). The
teaching record itself — `zero_method`, `zeroed_at`, `ee_pose`, `gain_profile` — stays defined
once, upstream; this band re-declares none of it.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.replay.replay import ReplayExecutor, build_replay
from backend.replay.waypoint import InterpolationMethod, ReplayWaypoint, TrajectorySpec
from backend.safety_bringup.constants import ARM_JOINT_COUNT
from backend.teaching.point import TeachingPoint
from backend.teaching.zero_match import ReplayVerdict, ZeroIdentity, evaluate_replay


class ZeroMatchBlockedError(Exception):
    """Raised when a taught point's zero reference no longer matches the robot's (WP-2D-05 gate).

    Attributes:
        verdicts: The BLOCKED replay verdicts, one per point the gate refused, each carrying
            the operator-facing reason.
    """

    def __init__(self, verdicts: tuple[ReplayVerdict, ...]) -> None:
        """Carry the blocking verdicts so the caller can show the operator warning."""
        self.verdicts = verdicts
        reasons = "; ".join(f"{verdict.point_name}: {verdict.reason}" for verdict in verdicts)
        super().__init__(f"replay blocked — zero reference changed since teaching: {reasons}")


def waypoint_from_teaching_point(point: TeachingPoint, dwell_s: float = 0.0) -> ReplayWaypoint:
    """Split a teaching point's `q_urdf[8]` into the arm-and-gripper replay waypoint.

    Args:
        point: The taught posture; its `q_urdf` is `MOTOR_ORDER` = seven arm joints then the
            gripper, in radians.
        dwell_s: Seconds to hold this posture during replay (a replay concern, not a taught
            field).

    Returns:
        (ReplayWaypoint) The interpolation input carrying the arm joints, the gripper, the side,
        and the dwell.
    """
    return ReplayWaypoint(
        arm_side=point.arm_side,
        q_arm=tuple(float(value) for value in point.q_urdf[:ARM_JOINT_COUNT]),
        gripper=float(point.q_urdf[ARM_JOINT_COUNT]),
        dwell_s=dwell_s,
        name=point.name,
    )


def spec_from_teaching_points(
    points: Sequence[TeachingPoint],
    method: InterpolationMethod = InterpolationMethod.LINEAR,
    rate_hz: float | None = None,
    segment_duration_s: float | None = None,
    velocity_scale: float = 1.0,
    other_arm_hold: tuple[float, ...] = (0.0,) * ARM_JOINT_COUNT,
    dwells: Sequence[float] | None = None,
) -> TrajectorySpec:
    """Build a trajectory spec from a teaching-point sequence.

    Args:
        points: The taught postures, at least two, all on one arm.
        method: The interpolation profile.
        rate_hz: The grid rate, or None for the default.
        segment_duration_s: The requested per-segment duration, or None for the default.
        velocity_scale: The velocity scale.
        other_arm_hold: The stationary arm's held configuration.
        dwells: Per-point dwell seconds, or None for no dwell.

    Returns:
        (TrajectorySpec) The spec ready to interpolate.

    Raises:
        ValueError: If `dwells` is given but does not match the point count.
    """
    if dwells is not None and len(dwells) != len(points):
        raise ValueError(f"dwells must match the {len(points)} points, got {len(dwells)}")
    dwell_values = list(dwells) if dwells is not None else [0.0] * len(points)
    waypoints = tuple(
        waypoint_from_teaching_point(point, dwell)
        for point, dwell in zip(points, dwell_values, strict=True)
    )
    fields: dict[str, object] = {
        "waypoints": waypoints,
        "method": method,
        "velocity_scale": velocity_scale,
        "other_arm_hold": other_arm_hold,
    }
    if rate_hz is not None:
        fields["rate_hz"] = rate_hz
    if segment_duration_s is not None:
        fields["segment_duration_s"] = segment_duration_s
    return TrajectorySpec(**fields)  # type: ignore[arg-type]


def build_replay_from_points(
    points: Sequence[TeachingPoint],
    current_zero: ZeroIdentity,
    method: InterpolationMethod = InterpolationMethod.LINEAR,
    rate_hz: float | None = None,
    segment_duration_s: float | None = None,
    velocity_scale: float = 1.0,
    other_arm_hold: tuple[float, ...] = (0.0,) * ARM_JOINT_COUNT,
    dwells: Sequence[float] | None = None,
    requested_margin_m: float | None = None,
    confirmed_zero_margin: bool = False,
    reference_qpos: list[float] | None = None,
) -> ReplayExecutor:
    """Gate a teaching sequence on zero-match, then interpolate, pre-verify, and build (①).

    The zero-match gate runs before anything else: every point is checked against the robot's
    current zero identity with the reused `WP-2D-05` gate, and any BLOCKED point stops the
    replay — the taught angles are not replayed under a zero the robot no longer holds. Only a
    fully-allowed sequence proceeds to interpolation and the four-check pre-verify.

    Args:
        points: The taught postures, at least two, all on one arm.
        current_zero: The robot's current zero identity for that arm.
        method: The interpolation profile.
        rate_hz: The grid rate, or None for the default.
        segment_duration_s: The requested per-segment duration, or None for the default.
        velocity_scale: The velocity scale.
        other_arm_hold: The stationary arm's held configuration.
        dwells: Per-point dwell seconds, or None for no dwell.
        requested_margin_m: Collision margin in metres, or None for the default.
        confirmed_zero_margin: Whether a zero margin was explicitly confirmed.
        reference_qpos: A collision-free reference configuration, or None for the model neutral.

    Returns:
        (ReplayExecutor) A ready executor for a zero-matched, pre-verified trajectory.

    Raises:
        ZeroMatchBlockedError: If any point's zero reference no longer matches the robot's.
        PreVerifyError: If the pre-verify fails (raised by `build_replay`).
    """
    verdicts = tuple(evaluate_replay(point, current_zero) for point in points)
    blocked = tuple(verdict for verdict in verdicts if not verdict.allowed)
    if blocked:
        raise ZeroMatchBlockedError(blocked)
    spec = spec_from_teaching_points(
        points,
        method=method,
        rate_hz=rate_hz,
        segment_duration_s=segment_duration_s,
        velocity_scale=velocity_scale,
        other_arm_hold=other_arm_hold,
        dwells=dwells,
    )
    return build_replay(spec, requested_margin_m, confirmed_zero_margin, reference_qpos)
