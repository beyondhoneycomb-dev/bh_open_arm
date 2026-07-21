"""Torque clamp in Nm and the explicit packet-scale crossing (WP-0A-04)."""

from __future__ import annotations

import pytest

from contracts.units import Nm, PacketTorque, clamp_torque, nm_to_packet, packet_to_nm


def test_clamp_bounds_above_and_below() -> None:
    """A torque past the limit is clamped to the signed limit magnitude."""
    assert clamp_torque(Nm(100.0), Nm(54.0)) == Nm(54.0)
    assert clamp_torque(Nm(-100.0), Nm(54.0)) == Nm(-54.0)


def test_clamp_passes_values_within_limit() -> None:
    """A torque inside the limit is returned unchanged."""
    assert clamp_torque(Nm(3.0), Nm(54.0)) == Nm(3.0)


def test_clamp_uses_limit_magnitude() -> None:
    """A negative limit clamps to the same symmetric interval as its magnitude."""
    assert clamp_torque(Nm(100.0), Nm(-54.0)) == Nm(54.0)


def test_packet_round_trip_is_identity() -> None:
    """packet -> Nm -> packet returns the original count for a fixed scale."""
    assert nm_to_packet(packet_to_nm(PacketTorque(1000), 0.01), 0.01) == PacketTorque(1000)


def test_packet_to_nm_applies_scale() -> None:
    """The packet scale is newton-metres per count."""
    assert packet_to_nm(PacketTorque(1000), 0.01) == Nm(10.0)


def test_nm_to_packet_rejects_zero_scale() -> None:
    """A zero scale has no inverse and is refused rather than dividing by zero."""
    with pytest.raises(ValueError, match="non-zero"):
        nm_to_packet(Nm(10.0), 0.0)
