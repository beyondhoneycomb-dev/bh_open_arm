"""WP-2D-05 acceptance suite — teaching-point schema + zero-match replay gate.

Shared builders. The core store and gate are pure (calibration + stdlib only), so most
of the suite runs with no optional dependency. Only the "same joint angle, different
pose" hazard demonstration reaches for the committed sim asset through the reused
WP-2D-01 FK (``backend.cartesian_jog``), and that module ``importorskip``s the sim
stack itself.
"""

from __future__ import annotations

from pathlib import Path

from backend.calibration import OpenArmCalibration, ZeroMethod
from backend.teaching import TeachingPoint, ZeroIdentity, capture_teaching_point

REPO_ROOT = Path(__file__).resolve().parents[2]
TEACHING_PACKAGE_DIR = REPO_ROOT / "backend" / "teaching"

RIGHT = "right"
LEFT = "left"

# Two distinct set-zero events. B is a later re-zero of the same arm; a point taught
# against A must not silently replay once the robot's record reads B.
ZEROED_AT_A = "2026-07-22T09:00:00+00:00"
ZEROED_AT_B = "2026-07-22T15:30:00+00:00"

_DEFAULT_POSE = [0.10, 0.20, 0.30, 1.0, 0.0, 0.0, 0.0]


def identity(
    side: str = RIGHT,
    method: ZeroMethod = ZeroMethod.LEROBOT_HANGING,
    zeroed_at: str | None = ZEROED_AT_A,
) -> ZeroIdentity:
    """Build a zero identity for one arm."""
    return ZeroIdentity(side=side, zero_method=method, zeroed_at=zeroed_at)


def sample_q(base: float = 0.0) -> list[float]:
    """Return an eight-wide joint command with distinct, non-trivial entries."""
    return [base + 0.1 * index for index in range(8)]


def make_point(
    name: str,
    side: str = RIGHT,
    zero: ZeroIdentity | None = None,
    q_urdf: list[float] | None = None,
    gain_profile: str = "default",
    q_lift: float = 0.15,
) -> TeachingPoint:
    """Capture a valid teaching point against a zero identity (the sanctioned path)."""
    zero = zero or identity(side)
    return capture_teaching_point(
        name=name,
        arm_side=side,
        q_urdf=q_urdf if q_urdf is not None else sample_q(),
        ee_pose=list(_DEFAULT_POSE),
        gain_profile=gain_profile,
        q_lift=q_lift,
        zero=zero,
    )


def make_calibration(
    side: str = RIGHT,
    last_zero_at: str | None = ZEROED_AT_A,
    method: ZeroMethod = ZeroMethod.LEROBOT_HANGING,
    urdf_zero_offset: list[float] | None = None,
) -> OpenArmCalibration:
    """Build a zero record whose identity a point can be gated against.

    ``urdf_zero_offset`` defaults asymmetrically per side so a left and a right record
    are never interchangeable — the asymmetry acceptance ③ turns on.
    """
    if urdf_zero_offset is None:
        urdf_zero_offset = [0.0] * 8 if side == RIGHT else [0.5, -0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0]
    return OpenArmCalibration(
        robot_type="oa_follower",
        robot_id=f"oa_{side}",
        side=side,
        motor_zero_raw=[0.0] * 8,
        urdf_zero_offset=urdf_zero_offset,
        gripper_open_rad=0.0,
        gripper_close_rad=-0.7854 if side == RIGHT else 0.7854,
        zero_method=method,
        last_zero_at=last_zero_at,
    )


__all__ = [
    "LEFT",
    "REPO_ROOT",
    "RIGHT",
    "TEACHING_PACKAGE_DIR",
    "ZEROED_AT_A",
    "ZEROED_AT_B",
    "identity",
    "make_calibration",
    "make_point",
    "sample_q",
]
