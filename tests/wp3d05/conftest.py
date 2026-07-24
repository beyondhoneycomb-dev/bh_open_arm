"""Shared fixtures for the WP-3D-05 integrity-verifier tests.

`materialized` is a READY dataset written once per module for the pass-path tests.
`fresh_dataset` is a factory the fault tests call to get an untouched dataset to
corrupt, since each fault injector mutates the tree in place.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.wp3d05.materialize import MaterializedDataset, materialize


@pytest.fixture(scope="module")
def materialized(tmp_path_factory: pytest.TempPathFactory) -> MaterializedDataset:
    """A READY packed three-episode dataset, written once for the module."""
    root: Path = tmp_path_factory.mktemp("integrity_ok")
    return materialize(root, episodes=3, frames=8)


@pytest.fixture()
def fresh_dataset(tmp_path: pytest.TempPathFactory) -> Callable[[], MaterializedDataset]:
    """A factory returning a fresh READY dataset each call, for a fault to corrupt."""
    counter = {"n": 0}

    def build() -> MaterializedDataset:
        root = Path(tmp_path) / f"ds{counter['n']}"
        counter["n"] += 1
        return materialize(root, episodes=3, frames=8)

    return build
