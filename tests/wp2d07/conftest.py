"""Shared fixtures and known configurations for the WP-2D-07 home tests.

The colliding start is a real, verified self-collision within the soft limits (the right arm
at joint4 = 2.3 rad folds link3 into itself), not a stub: the pre-verify failure it drives is
the genuine WP-2D-06 four-check walk — whose collision half is WP-2C-08 — refusing, which is
what acceptance ② requires.
"""

from __future__ import annotations

import math

import pytest

from backend.cartesian_jog.frames import KinematicFrames
from backend.home.homereturn import HomeReturn
from backend.home.preverify import HomePreflight
from backend.home.profile import HomeProfileRegistry, default_registry

# right joint1..7 then left joint1..7 — the 14 arm DOF a home return moves.
HOME_ARM = (0.0, 0.0, 0.0, math.pi / 2, 0.0, 0.0, 0.0)
SAFE_START = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0) * 2
BENIGN_WAYPOINT = (0.0, 0.0, 0.0, 1.2, 0.0, 0.0, 0.0) * 2
# Right arm within its soft limits but self-colliding; left arm already at home.
COLLIDING_START = (0.0, 0.6, 0.0, 2.3, 0.0, 0.0, 0.0) + HOME_ARM


@pytest.fixture(scope="session")
def frames() -> KinematicFrames:
    """The reused WP-2D-01 FK context over the committed cell asset."""
    return KinematicFrames()


@pytest.fixture(scope="session")
def preflight() -> HomePreflight:
    """The home pre-verify caller over the reused WP-2D-06 four-check walk."""
    return HomePreflight()


@pytest.fixture
def registry() -> HomeProfileRegistry:
    """A fresh registry seeded with the default home as the active profile."""
    return default_registry()


@pytest.fixture
def home(
    registry: HomeProfileRegistry, preflight: HomePreflight, frames: KinematicFrames
) -> HomeReturn:
    """A home-return bound to the default registry, reused pre-verify, and reused FK."""
    return HomeReturn(registry, preflight, frames)
