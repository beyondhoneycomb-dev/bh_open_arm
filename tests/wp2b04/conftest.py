"""Shared fixtures for the WP-2B-04 payload-model acceptance tests.

Poses are right-arm, v2 joint convention, radians — the convention WP-2B-02's `tau_grav`
computes in and the payload model reflects onto. The worst-extension pose reaches the arm out
horizontally (shoulder joint2 at +pi/2, elbow joint3 at -pi/2), the configuration that
maximises shoulder gravity torque and so drives the effort-saturation preflight.
"""

from __future__ import annotations

import math

import pytest

from backend.gravity import Arm
from backend.payload import PayloadGravityModel

# In-limit right-arm poses, radians, joint1..joint7 (limits from the committed v2 MJCF).
_POSE_GRID = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1),
    (-0.5, 0.2, 0.9, 1.5, -0.7, 0.4, -1.0),
    (1.0, 1.5708, 0.0, 1.2, 1.0, 0.5, 0.6),
)


@pytest.fixture
def right_model() -> PayloadGravityModel:
    """A fresh right-arm payload gravity model with an empty registry."""
    return PayloadGravityModel(Arm.RIGHT)


@pytest.fixture
def pose_grid() -> tuple[tuple[float, ...], ...]:
    """A small grid of in-limit right-arm poses, radians."""
    return _POSE_GRID


@pytest.fixture
def worst_extension_pose() -> tuple[float, ...]:
    """The shoulder-out-horizontal pose that maximises gravity torque, radians."""
    return (0.0, math.pi / 2.0, -math.pi / 2.0, 0.0, 0.0, 0.0, 0.0)


@pytest.fixture
def folded_pose() -> tuple[float, ...]:
    """A compact pose whose gravity torque is small on every joint, radians."""
    return (0.0, 0.0, 0.0, 1.2, 0.0, 0.0, 0.0)
