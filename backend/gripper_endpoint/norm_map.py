"""The gripper norm[0,1] <-> native-rad linear map (FR-MAN-016, `03` FR-MOT-062).

The two hand-captured endpoint rads anchor the map: norm 0 is the open endpoint,
norm 1 the close endpoint, and `rad(norm) = open + clamp01(norm)*(close - open)`.
Opening amount in mm and the motor:finger ratio are deliberately absent — the map is
defined by the captured endpoints alone, so control holds without either (FR-MAN-016);
that is the whole point of capturing endpoints instead of trusting a driver constant.
"""

from __future__ import annotations

from backend.gripper_endpoint.constants import (
    MIN_ENDPOINT_SEPARATION_RAD,
    NORM_MAX,
    NORM_MIN,
)
from backend.gripper_endpoint.errors import GripperConfigError


def clamp01(value: float) -> float:
    """Clamp a normalized command into [0, 1].

    Args:
        value: A normalized open/close command.

    Returns:
        (float) `value` saturated to the [0, 1] domain.
    """
    return max(NORM_MIN, min(NORM_MAX, value))


def norm_to_rad(norm: float, open_rad: float, close_rad: float) -> float:
    """Map a normalized open/close command to a native gripper rad.

    The command is clamped to [0, 1] first, so an out-of-range norm saturates at an
    endpoint rather than commanding past a mechanical stop (FR-MAN-016).

    Args:
        norm: The normalized command (0 = open endpoint, 1 = close endpoint).
        open_rad: Native rad captured at the physical open stop.
        close_rad: Native rad captured at the physical close stop.

    Returns:
        (float) The native gripper rad for this command.
    """
    return open_rad + clamp01(norm) * (close_rad - open_rad)


def rad_to_norm(rad: float, open_rad: float, close_rad: float) -> float:
    """Map a native gripper rad back to a normalized command in [0, 1].

    Args:
        rad: A native gripper rad.
        open_rad: Native rad captured at the physical open stop.
        close_rad: Native rad captured at the physical close stop.

    Returns:
        (float) The normalized command, clamped to [0, 1].

    Raises:
        GripperConfigError: If the endpoints coincide, leaving the map undefined.
    """
    span = close_rad - open_rad
    if abs(span) < MIN_ENDPOINT_SEPARATION_RAD:
        raise GripperConfigError(
            "gripper endpoints coincide; the norm map is undefined "
            f"(open_rad={open_rad}, close_rad={close_rad})"
        )
    return clamp01((rad - open_rad) / span)
