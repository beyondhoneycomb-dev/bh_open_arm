"""Gripper POS_FORCE limit exposure: a speed cap clamp and a per-unit force cap.

LeRobot sends all eight motors (gripper included) as MIT, so POS_FORCE gripper
control is a `send_action()` bypass (FR-MOT-046); this module owns the two limits
that bypass exposes — a speed cap clamped to the DM4310 register V_MAX and a force
cap in the per-unit domain [0, 1].

It re-implements no arm safety primitive. The arm jog-path velocity check/clamp
(`backend.actuation` SafetyFilter / SafetyLimits) rejects a per-joint position step
on the 8-motor command vector; this is a scalar ceiling clamp on a single
actuator's commanded open/close speed — a different quantity on a different
(POS_FORCE bypass) command path. The one shared truth, the DM4310 V_MAX, is
imported from the CAN register table, not restated.
"""

from __future__ import annotations

from backend.gripper_endpoint.constants import (
    GRIPPER_SPEED_CAP_RAD_S,
    TORQUE_PU_MAX,
    TORQUE_PU_MIN,
)
from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.labels import FORCE_VALUE_LABEL, SPEED_CAP_LABEL


def clamp_speed_rad_s(requested: float) -> float:
    """Clamp a requested gripper speed to the DM4310 register V_MAX ceiling.

    A negative request is a malformed command, not a direction, so it is refused
    rather than clamped — clamping it would silently make it a valid low speed.

    Args:
        requested: The requested POS_FORCE speed cap, rad/s.

    Returns:
        (float) `requested` capped at the DM4310 V_MAX ceiling.

    Raises:
        GripperConfigError: If `requested` is negative.
    """
    if requested < 0.0:
        raise GripperConfigError(f"gripper speed cap must be non-negative, got {requested}")
    return min(requested, GRIPPER_SPEED_CAP_RAD_S)


def speed_was_clamped(requested: float) -> bool:
    """Report whether a requested speed exceeded the ceiling and would be clamped.

    Args:
        requested: The requested POS_FORCE speed cap, rad/s.

    Returns:
        (bool) True when `requested` is above the DM4310 V_MAX ceiling.
    """
    return requested > GRIPPER_SPEED_CAP_RAD_S


def validate_torque_pu(torque_pu: float) -> float:
    """Return the per-unit force cap, refusing any value outside [0, 1].

    A value outside [0, 1] is a physical-force-unit intrusion — the per-unit-to-force
    constant is undetermined and no load cell is used — so it is refused (FR-MAN-016,
    FR-SAF-024b). That refusal is the "load-cell force calibration attempt is out of
    range" negative branch.

    Args:
        torque_pu: The requested force cap in per-unit terms.

    Returns:
        (float) `torque_pu`, once confirmed to be in [0, 1].

    Raises:
        GripperConfigError: If `torque_pu` is outside [0, 1].
    """
    if not TORQUE_PU_MIN <= torque_pu <= TORQUE_PU_MAX:
        raise GripperConfigError(
            f"gripper force cap must be per-unit in [{TORQUE_PU_MIN}, {TORQUE_PU_MAX}], "
            f"got {torque_pu}; a physical force unit is not accepted"
        )
    return torque_pu


def format_force_status(torque_pu: float) -> str:
    """Render a user-facing gripper force line — per-unit, never a physical unit.

    Args:
        torque_pu: A per-unit force value in [0, 1].

    Returns:
        (str) A per-unit force status line.
    """
    return f"{FORCE_VALUE_LABEL}: {validate_torque_pu(torque_pu):.3f}"


def format_speed_status(requested: float) -> str:
    """Render a user-facing gripper speed-cap line at the effective (clamped) value.

    Args:
        requested: The requested POS_FORCE speed cap, rad/s.

    Returns:
        (str) A speed-cap status line carrying the clamped effective value.
    """
    return f"{SPEED_CAP_LABEL}: {clamp_speed_rad_s(requested):.3f}"
