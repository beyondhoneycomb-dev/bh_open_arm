"""Numeric correctness of the named unit conversions (WP-0A-04)."""

from __future__ import annotations

import math

import pytest

from contracts.units import (
    Deg,
    DegPerSec,
    Rad,
    RadPerSec,
    deg_per_sec_to_rad_per_sec,
    deg_to_rad,
    rad_per_sec_to_deg_per_sec,
    rad_to_deg,
)


def test_deg_to_rad_half_turn_is_pi() -> None:
    """180 degrees is pi radians."""
    assert math.isclose(deg_to_rad(Deg(180.0)).value, math.pi)


def test_rad_to_deg_pi_is_half_turn() -> None:
    """pi radians is 180 degrees."""
    assert math.isclose(rad_to_deg(Rad(math.pi)).value, 180.0)


@pytest.mark.parametrize("degrees", [0.0, 1.0, 45.0, 90.0, -135.0, 359.9])
def test_angle_round_trip_is_identity(degrees: float) -> None:
    """deg -> rad -> deg returns the original angle within tolerance."""
    assert math.isclose(rad_to_deg(deg_to_rad(Deg(degrees))).value, degrees, abs_tol=1e-9)


def test_velocity_conversion_matches_angle_factor() -> None:
    """Angular velocity converts by the same 180/pi factor as angle."""
    assert math.isclose(deg_per_sec_to_rad_per_sec(DegPerSec(180.0)).value, math.pi)
    assert math.isclose(rad_per_sec_to_deg_per_sec(RadPerSec(math.pi)).value, 180.0)


def test_conversion_returns_the_other_unit() -> None:
    """A conversion yields the target tag type, never the source."""
    assert isinstance(deg_to_rad(Deg(1.0)), Rad)
    assert isinstance(rad_to_deg(Rad(1.0)), Deg)
    assert isinstance(deg_per_sec_to_rad_per_sec(DegPerSec(1.0)), RadPerSec)
    assert isinstance(rad_per_sec_to_deg_per_sec(RadPerSec(1.0)), DegPerSec)
