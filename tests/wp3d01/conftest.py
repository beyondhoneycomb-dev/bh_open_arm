"""Shared fixtures for the WP-3D-01 episode-viewer tests.

A single materialized on-disk dataset (two packed episodes, two RGB cameras and a
depth camera) is written once per test module and handed to the tests, so each
one exercises the direct reader against a real parquet/mp4/tiff tree rather than a
mock.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.wp3d01.materialize import MaterializedDataset, materialize


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> MaterializedDataset:
    """Materialize a packed two-episode dataset once for a test module."""
    root: Path = tmp_path_factory.mktemp("viewer_dataset")
    return materialize(root, episodes=2, frames=8)


@pytest.fixture()
def episode0(dataset: MaterializedDataset) -> Iterator[object]:
    """Open episode 0 of the materialized dataset, closed after the test."""
    from backend.dataset.viewer import EpisodeViewer

    viewer = EpisodeViewer.open(dataset.root, 0)
    try:
        yield viewer
    finally:
        viewer.close()


@pytest.fixture()
def episode1(dataset: MaterializedDataset) -> Iterator[object]:
    """Open episode 1 (the packed, offset episode), closed after the test."""
    from backend.dataset.viewer import EpisodeViewer

    viewer = EpisodeViewer.open(dataset.root, 1)
    try:
        yield viewer
    finally:
        viewer.close()
