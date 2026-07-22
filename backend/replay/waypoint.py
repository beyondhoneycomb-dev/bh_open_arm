"""The replay input contract: waypoints and a trajectory spec (WP-2D-06).

This band interpolates a sparse sequence of joint targets into a dense, pre-verified
trajectory. The input it consumes is the *replay* view of a teaching point, not the
persisted teaching record: `WP-2D-05` owns the schema
(`{name, arm_side, q_urdf[8], ee_pose[7], gain_profile, zero_method, zeroed_at, q_lift,
timestamp}`) and the zero-mismatch playback gate that runs *before* replay. A `ReplayWaypoint`
carries only what the interpolator needs — the arm side, the seven arm joints and the gripper
(the `q_urdf[8]` split), and the per-waypoint dwell — so the teaching schema stays defined in
one place upstream and is not re-declared here.

The trajectory is single-arm: one side moves and the other is held at a fixed configuration
so the collision pre-verify has both arms to check. Bimanual replay is two specs, not a
wider waypoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.replay.constants import (
    DEFAULT_RATE_HZ,
    DEFAULT_SEGMENT_DURATION_S,
    FULL_VELOCITY_SCALE,
    MIN_VELOCITY_SCALE,
)
from backend.safety_bringup.constants import ARM_JOINT_COUNT

SIDES = ("right", "left")


class InterpolationMethod(Enum):
    """The interpolation profile between two waypoints.

    All three are built (`02b` WP-2D-06 acceptance is `ACCEPTED`, not `DEGRADED`): linear is
    the residual-polluting default, cubic zeroes endpoint velocity, quintic zeroes endpoint
    velocity and acceleration.
    """

    LINEAR = "linear"
    CUBIC = "cubic"
    QUINTIC = "quintic"


@dataclass(frozen=True)
class ReplayWaypoint:
    """One target in a replay sequence — the interpolation view of a teaching point.

    Attributes:
        arm_side: `"right"` or `"left"` — the arm this waypoint commands.
        q_arm: The seven arm-joint angles, joint1..joint7, radians (the `q_urdf[8]` arm part).
        gripper: The gripper (finger driver) angle, radians (the `q_urdf[8]` eighth value).
        dwell_s: Seconds to hold this configuration after arriving, before the next segment.
        name: Optional teaching-point name carried through for the operator log.
    """

    arm_side: str
    q_arm: tuple[float, ...]
    gripper: float
    dwell_s: float = 0.0
    name: str = ""

    def __post_init__(self) -> None:
        """Reject a waypoint whose side, joint count, or dwell is malformed."""
        if self.arm_side not in SIDES:
            raise ValueError(f"arm_side must be 'right' or 'left', got {self.arm_side!r}")
        if len(self.q_arm) != ARM_JOINT_COUNT:
            raise ValueError(f"q_arm must hold {ARM_JOINT_COUNT} joints, got {len(self.q_arm)}")
        if self.dwell_s < 0.0:
            raise ValueError(f"dwell_s must be non-negative, got {self.dwell_s}")


@dataclass(frozen=True)
class TrajectorySpec:
    """A multi-point replay sequence and how to interpolate it (`02b` WP-2D-06).

    Attributes:
        waypoints: The sequence, at least two, all on the same arm side.
        method: The interpolation profile.
        rate_hz: The interpolation grid rate; default 50 Hz.
        segment_duration_s: The planned per-segment duration before any velocity-scale
            extension; default 2 s.
        velocity_scale: Fraction of the velocity ceiling the motion may use, in
            (MIN_VELOCITY_SCALE, 1]. A smaller scale auto-extends the duration (②).
        other_arm_hold: The stationary arm's seven joint angles, held for the whole
            trajectory so the collision pre-verify has both arms; defaults to zeros.
    """

    waypoints: tuple[ReplayWaypoint, ...]
    method: InterpolationMethod = InterpolationMethod.LINEAR
    rate_hz: float = DEFAULT_RATE_HZ
    segment_duration_s: float = DEFAULT_SEGMENT_DURATION_S
    velocity_scale: float = FULL_VELOCITY_SCALE
    other_arm_hold: tuple[float, ...] = field(default_factory=lambda: (0.0,) * ARM_JOINT_COUNT)

    def __post_init__(self) -> None:
        """Reject a spec that cannot form a trajectory: too few, mixed-side, or bad scaling."""
        if len(self.waypoints) < 2:
            raise ValueError("a trajectory needs at least two waypoints")
        sides = {waypoint.arm_side for waypoint in self.waypoints}
        if len(sides) != 1:
            raise ValueError(f"all waypoints must share one arm side, got {sorted(sides)}")
        if self.rate_hz <= 0.0:
            raise ValueError(f"rate_hz must be positive, got {self.rate_hz}")
        if self.segment_duration_s <= 0.0:
            raise ValueError(f"segment_duration_s must be positive, got {self.segment_duration_s}")
        if not MIN_VELOCITY_SCALE <= self.velocity_scale <= FULL_VELOCITY_SCALE:
            raise ValueError(
                f"velocity_scale must be in [{MIN_VELOCITY_SCALE}, {FULL_VELOCITY_SCALE}], "
                f"got {self.velocity_scale}"
            )
        if len(self.other_arm_hold) != ARM_JOINT_COUNT:
            raise ValueError(
                f"other_arm_hold must hold {ARM_JOINT_COUNT} joints, got {len(self.other_arm_hold)}"
            )

    @property
    def arm_side(self) -> str:
        """The single arm side every waypoint commands."""
        return self.waypoints[0].arm_side


def dwell_sample_count(dwell_s: float, rate_hz: float) -> int:
    """Return how many held grid samples a dwell occupies.

    Args:
        dwell_s: The dwell duration, seconds.
        rate_hz: The interpolation grid rate, hertz.

    Returns:
        (int) The number of extra held samples, `round(dwell_s * rate_hz)`, never negative.
    """
    return max(0, round(dwell_s * rate_hz))
