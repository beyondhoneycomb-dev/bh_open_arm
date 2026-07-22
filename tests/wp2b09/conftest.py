"""Shared fixtures for the WP-2B-09 scale-separation acceptance tests.

The pose grid is a small set of in-limit right-arm poses in the v2 joint convention (the same
grid shape WP-2B-02 uses). The friction vector is synthetic: WP-2B-09 owns no friction
identification — real per-joint `tau_fric(ω)` comes from WP-2B-07 (`PG-FRIC-001`, hardware-gated).
These tests exercise the scale-separation arithmetic, so a representative non-zero friction vector
is enough and is marked provisional here rather than presented as an identified value.
"""

from __future__ import annotations

import pytest

_POSE_GRID = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1),
    (-0.5, 0.2, 0.9, 1.5, -0.7, 0.4, -1.0),
    (1.0, 1.5708, 0.0, 1.2, 1.0, 0.5, 0.6),
    (-1.0, 2.8, -1.2, 2.0, -1.3, -0.6, 1.2),
)

# A representative per-joint friction torque [Nm], joint1..joint7. Synthetic and provisional —
# not an identified PG-FRIC-001 fit. Non-zero and mixed-sign so a dropped or mis-scaled friction
# term shows up in the separation arithmetic.
_SYNTHETIC_FRICTION_TAU = (2.0, -1.5, 1.0, 0.5, -0.3, 0.2, -0.1)


@pytest.fixture
def pose_grid() -> tuple[tuple[float, ...], ...]:
    """A small grid of in-limit right-arm poses, radians."""
    return _POSE_GRID


@pytest.fixture
def moving_velocity() -> tuple[float, ...]:
    """A non-zero joint-velocity vector so the Coriolis term is non-trivial, rad/s."""
    return (0.8,) * 7


@pytest.fixture
def synthetic_friction() -> tuple[float, ...]:
    """A provisional per-joint friction torque vector, Nm (not a PG-FRIC-001 fit)."""
    return _SYNTHETIC_FRICTION_TAU
