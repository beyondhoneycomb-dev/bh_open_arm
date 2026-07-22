"""The norm[0,1] <-> native-rad linear map (FR-MAN-016, `03` FR-MOT-062).

norm 0 is the open endpoint, norm 1 the close endpoint, and the map is linear between
them. An out-of-range command saturates at an endpoint (it is clamped, not
extrapolated), and a degenerate capture whose endpoints coincide is refused.
"""

from __future__ import annotations

import math

import pytest

from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.norm_map import clamp01, norm_to_rad, rad_to_norm

_OPEN = 0.0
_CLOSE = -math.pi / 2


def test_endpoints_map_to_norm_0_and_1() -> None:
    """norm 0 lands on the open rad and norm 1 on the close rad."""
    assert norm_to_rad(0.0, _OPEN, _CLOSE) == pytest.approx(_OPEN)
    assert norm_to_rad(1.0, _OPEN, _CLOSE) == pytest.approx(_CLOSE)


def test_midpoint_is_linear() -> None:
    """norm 0.5 is exactly halfway between the endpoints."""
    assert norm_to_rad(0.5, _OPEN, _CLOSE) == pytest.approx((_OPEN + _CLOSE) / 2)


def test_out_of_range_norm_saturates_at_endpoints() -> None:
    """A command below 0 or above 1 clamps to an endpoint, not past a mechanical stop."""
    assert norm_to_rad(-3.0, _OPEN, _CLOSE) == pytest.approx(_OPEN)
    assert norm_to_rad(4.0, _OPEN, _CLOSE) == pytest.approx(_CLOSE)


def test_norm_and_rad_round_trip() -> None:
    """rad_to_norm inverts norm_to_rad across the interior of the range."""
    for norm in (0.0, 0.2, 0.5, 0.9, 1.0):
        rad = norm_to_rad(norm, _OPEN, _CLOSE)
        assert rad_to_norm(rad, _OPEN, _CLOSE) == pytest.approx(norm)


def test_clamp01_bounds() -> None:
    """clamp01 saturates to the [0, 1] domain."""
    assert clamp01(-0.1) == 0.0
    assert clamp01(1.7) == 1.0
    assert clamp01(0.3) == 0.3


def test_degenerate_capture_is_refused() -> None:
    """Coincident endpoints leave the map undefined and are refused, not divided by zero."""
    with pytest.raises(GripperConfigError, match="undefined"):
        rad_to_norm(0.1, 0.5, 0.5)
