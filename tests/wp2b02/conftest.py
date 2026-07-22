"""Shared fixtures for the WP-2B-02 gravity-backend acceptance tests.

The pose grid is a small set of representative right-arm poses inside the v2 joint limits
(read from `sim/mjcf/v2/openarm_bimanual.xml`), including the extended shoulder where gravity
torque is largest. Poses are in the v2 joint convention — the convention the backend verifies
and computes in.
"""

from __future__ import annotations

import pytest

# Right-arm v2 joint limits [rad], joint1..joint7, from the committed v2 MJCF.
RIGHT_ARM_LIMITS = (
    (-1.3963, 3.4907),
    (-0.17453, 3.3161),
    (-1.5708, 1.5708),
    (0.0, 2.4435),
    (-1.5708, 1.5708),
    (-0.7854, 0.7854),
    (-1.5708, 1.5708),
)

_POSE_GRID = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1),
    (-0.5, 0.2, 0.9, 1.5, -0.7, 0.4, -1.0),
    (1.0, 1.5708, 0.0, 1.2, 1.0, 0.5, 0.6),
    (-1.0, 2.8, -1.2, 2.0, -1.3, -0.6, 1.2),
)


@pytest.fixture
def zero_pose() -> tuple[float, ...]:
    """The all-zero right-arm pose, radians."""
    return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@pytest.fixture
def pose_grid() -> tuple[tuple[float, ...], ...]:
    """A small grid of in-limit right-arm poses, radians."""
    return _POSE_GRID
