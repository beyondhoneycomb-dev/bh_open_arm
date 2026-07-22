"""Shared fixtures for the WP-1-06 extended-safety-bring-up tests.

The committed MJCF path (READ only — WP-0C-03 owns it), the injected sim/safety asset
paths, and a temp-dir injector so an asset check can run against freshly injected bytes
without depending on the committed copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.safety_bringup import committed_mjcf_path

REPO_ROOT = Path(__file__).resolve().parents[2]
INJECTED_URDF = REPO_ROOT / "sim" / "safety" / "urdf" / "openarm_link7_collision.urdf"
INJECTED_WALLS = REPO_ROOT / "sim" / "safety" / "scene" / "virtual_walls.xml"


@pytest.fixture
def committed_mjcf() -> Path:
    """The vendored MJCF the link7 check READs (never writes), located via its owning package."""
    return committed_mjcf_path()


@pytest.fixture
def injected_urdf() -> Path:
    """The committed link7 collision descriptor under sim/safety."""
    return INJECTED_URDF


@pytest.fixture
def injected_walls() -> Path:
    """The committed virtual-wall scene fragment under sim/safety."""
    return INJECTED_WALLS
