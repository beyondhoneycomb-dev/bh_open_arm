"""Shared builders for the WP-2D-03 acceptance suite.

The gravity backend loads mujoco, so a module that builds one ``importorskip``s it first; this
support module keeps that import lazy (inside the builder) so importing it costs nothing. The
arm safety limits are a valid single-arm (7-joint) envelope whose peak torque is the canonical
follower peak torque for the arm joints — the same source the gateway clamp and the effort check
both read, never a second copy invented here.
"""

from __future__ import annotations

from functools import lru_cache

from backend.actuation.safety import SafetyLimits
from contracts.units import Deg, Nm

# The seven arm-joint peak torques (Nm), matching the follower's PEAK_TORQUE_NM arm entries.
ARM_PEAK_TORQUE_NM = (40.0, 40.0, 27.0, 27.0, 10.0, 10.0, 10.0)

# A neutral, well-inside-limits entry pose and zero velocity for the arm's seven joints.
ENTRY_POSE_RAD = (0.0, 0.3, 0.0, 0.5, 0.0, 0.2, 0.0)
ENTRY_VELOCITY_RAD_S = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

_ARM_WIDTH = len(ARM_PEAK_TORQUE_NM)


def arm_safety_limits(peak_scale: float = 1.0) -> SafetyLimits:
    """Build a valid single-arm safety envelope.

    Args:
        peak_scale: A multiplier on the peak torque, so a test can shrink the effort envelope
            enough to force a saturation at a normal pose.

    Returns:
        (SafetyLimits) A validated 7-joint envelope.
    """
    mechanical = tuple((Deg(-180.0), Deg(180.0)) for _ in range(_ARM_WIDTH))
    operational = tuple((Deg(-170.0), Deg(170.0)) for _ in range(_ARM_WIDTH))
    peak = tuple(Nm(value * peak_scale) for value in ARM_PEAK_TORQUE_NM)
    limits = SafetyLimits(
        mechanical_deg=mechanical,
        operational_deg=operational,
        velocity_limit_rad_s=tuple(3.0 for _ in range(_ARM_WIDTH)),
        accel_limit_rad_s2=tuple(20.0 for _ in range(_ARM_WIDTH)),
        jerk_limit_rad_s3=tuple(200.0 for _ in range(_ARM_WIDTH)),
        step_delta_limit_rad=tuple(1.8 for _ in range(_ARM_WIDTH)),
        peak_torque_nm=peak,
        operational_torque_nm=peak,
    )
    limits.validate()
    return limits


@lru_cache(maxsize=1)
def gravity_backend():  # noqa: ANN201  (return type would import mujoco at annotation time)
    """Build (and cache) the v2 gravity backend for the right arm.

    Returns:
        The MuJoCo v2 gravity backend; cached so the MJCF loads once across the suite.
    """
    from backend.gravity import Arm, BackendId, select_backend

    return select_backend(BackendId.MUJOCO_V2, Arm.RIGHT)


def friction_seed():  # noqa: ANN201  (kept parallel to gravity_backend's lazy shape)
    """Return the per-joint friction seed used as the identified-law stand-in.

    Returns:
        The v1 friction seed, seven joints.
    """
    from backend.friction import V1_SEED_FRICTION

    return V1_SEED_FRICTION
