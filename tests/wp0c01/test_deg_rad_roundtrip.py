"""Acceptance ③ -- deg<->rad round-trip: rad -> deg -> rad within numerical limits.

The conversion crossing the LeRobot<->MJCF boundary must be lossless to numerical
precision: a radian value taken to degrees and back is the same radian. This tests
the CTR-UNIT named conversions the boundary uses, and the sim-sync wrappers that
carry a full position action across and back.
"""

from __future__ import annotations

import math

import pytest

from contracts.units import Deg, Rad, deg_to_rad, rad_to_deg
from sim.mujoco.sim_sync import action_channel_order, lerobot_to_mjcf, mjcf_to_lerobot

# The tightest tolerance the double round-trip holds to; two math.radians/degrees
# passes stay well inside this.
_PRECISION = 1e-12

_RAD_SAMPLES = (
    -math.pi,
    -1.5707963267948966,
    -0.3,
    0.0,
    0.04,
    1.0,
    1.5707963267948966,
    3.3161,
)


@pytest.mark.parametrize("radians", _RAD_SAMPLES)
def test_rad_deg_rad_roundtrip_is_lossless(radians: float) -> None:
    restored = deg_to_rad(rad_to_deg(Rad(radians)))
    assert abs(restored.value - radians) < _PRECISION


@pytest.mark.parametrize("degrees", (-180.0, -90.0, -5.0, 0.0, 12.5, 90.0, 179.99))
def test_deg_rad_deg_roundtrip_is_lossless(degrees: float) -> None:
    restored = rad_to_deg(deg_to_rad(Deg(degrees)))
    assert abs(restored.value - degrees) < _PRECISION


def test_sim_sync_action_crosses_and_returns_unchanged() -> None:
    # A full 16-channel position action in degrees, taken to MJCF radians and read
    # back through the observation crossing, returns to the same degrees.
    action_deg = {name: (index * 1.25 - 8.0) for index, name in enumerate(action_channel_order())}
    ctrl_rad = lerobot_to_mjcf(action_deg)

    # Feed each channel's radian as the joint position of a synthetic state.
    joint_state = {name.removesuffix(".pos"): (ctrl_rad[name], 0.0, 0.0) for name in action_deg}
    observation = mjcf_to_lerobot(joint_state)

    for name, degrees in action_deg.items():
        assert abs(observation[name] - degrees) < _PRECISION
