"""Shared fixtures for the WP-2B-08 path-B bootstrap acceptance tests.

Poses are right-arm, v2 joint convention, radians — the convention the reused WP-2B-02 backend
verifies and computes in. The extended pose puts the shoulder (joint2) out where gravity torque
is largest, so a stubbed or zeroed inertia model cannot pass the "v2-inertia-based" checks. The
velocity is chosen to make the Coriolis term non-zero, separating gravity+Coriolis from gravity
alone.
"""

from __future__ import annotations

import pytest

from backend.pathb import PathBBootstrap


@pytest.fixture
def bootstrap() -> PathBBootstrap:
    """A right-arm path-B bootstrap loaded on the committed v2 MJCF."""
    return PathBBootstrap()


@pytest.fixture
def extended_pose() -> tuple[float, ...]:
    """A right-arm pose with the shoulder extended (large gravity torque), radians."""
    return (0.0, 1.5708, 0.0, 1.2, 0.0, 0.0, 0.0)


@pytest.fixture
def zero_velocity() -> tuple[float, ...]:
    """The all-zero right-arm joint velocity, rad/s."""
    return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@pytest.fixture
def moving_velocity() -> tuple[float, ...]:
    """A right-arm joint velocity that yields a non-zero Coriolis term, rad/s."""
    return (0.5, 0.3, -0.2, 0.1, 0.0, 0.4, -0.1)
