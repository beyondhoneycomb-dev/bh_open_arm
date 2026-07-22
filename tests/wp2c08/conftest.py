"""Shared fixtures for the WP-2C-08 collision-preflight tests."""

from __future__ import annotations

import pytest

from backend.collision_preflight.model import PreflightModel
from backend.safety_bringup.constants import COLLISION_MARGIN_DEFAULT_M


@pytest.fixture
def preflight_model() -> PreflightModel:
    """A preflight model loaded at the default collision margin."""
    return PreflightModel(COLLISION_MARGIN_DEFAULT_M)
