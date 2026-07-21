"""The only sanctioned crossings between degree and radian tag types.

Every rad-deg boundary the plan names (`contracts/unit_tags.yaml`) routes through
exactly one of these functions. They are the sole place a value changes unit; the
tag types themselves offer no implicit path, so a conversion that does not appear
here does not exist. Keeping the crossing named — rather than an arithmetic
expression buried at a call site — is what lets the boundary table assert that a
boundary has one conversion site and not two (`FR-SIM-082`).
"""

from __future__ import annotations

import math

from contracts.units.tags import Deg, DegPerSec, Rad, RadPerSec


def deg_to_rad(angle: Deg) -> Rad:
    """Convert a degree angle to radians.

    Args:
        angle: An angle in degrees.

    Returns:
        (Rad) The same angle in radians.
    """
    return Rad(math.radians(angle.value))


def rad_to_deg(angle: Rad) -> Deg:
    """Convert a radian angle to degrees.

    Args:
        angle: An angle in radians.

    Returns:
        (Deg) The same angle in degrees.
    """
    return Deg(math.degrees(angle.value))


def deg_per_sec_to_rad_per_sec(velocity: DegPerSec) -> RadPerSec:
    """Convert an angular velocity from degrees per second to radians per second.

    Args:
        velocity: An angular velocity in degrees per second.

    Returns:
        (RadPerSec) The same velocity in radians per second.
    """
    return RadPerSec(math.radians(velocity.value))


def rad_per_sec_to_deg_per_sec(velocity: RadPerSec) -> DegPerSec:
    """Convert an angular velocity from radians per second to degrees per second.

    Args:
        velocity: An angular velocity in radians per second.

    Returns:
        (DegPerSec) The same velocity in degrees per second.
    """
    return DegPerSec(math.degrees(velocity.value))
