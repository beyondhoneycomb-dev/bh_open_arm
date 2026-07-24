"""Shared fixtures for the WP-3C-06 source-delete interlock acceptance suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.wp3c06.materialize import Fixture, materialize


@pytest.fixture
def pair(tmp_path: Path) -> Fixture:
    """A faithful raw-source / converted-READY-dataset pair (two episodes, eight frames).

    Each test gets its own on-disk pair so a fault injector can mutate one facet
    without leaking into another test.
    """
    return materialize(tmp_path, episodes=2, frames=8, include_depth=True)
