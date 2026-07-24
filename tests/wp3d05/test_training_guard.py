"""An INVALID dataset is never exposed as a training input (`02b` §8.2 WP-3D-05 ②).

`ensure_training_ready` is the interlock WP-3C-06 (source-delete) consumes: it must
raise on any INVALID dataset and return only for a READY one. The raised error must
name the failing check so the interlock can log why the dataset was barred.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.dataset.integrity import (
    CHECK_STATS_HASH_MATCH,
    IntegrityError,
    ensure_training_ready,
)
from tests.wp3d05 import faults
from tests.wp3d05.materialize import MaterializedDataset


def test_guard_raises_on_invalid_dataset(
    fresh_dataset: Callable[[], MaterializedDataset],
) -> None:
    dataset = fresh_dataset()
    faults.inject_stats_hash_mismatch(dataset)

    with pytest.raises(IntegrityError) as caught:
        ensure_training_ready(dataset.root)

    assert CHECK_STATS_HASH_MATCH in str(caught.value)


def test_guard_returns_report_on_ready_dataset(materialized: MaterializedDataset) -> None:
    report = ensure_training_ready(materialized.root)
    assert report.ready is True


def test_guard_raises_when_dataset_missing(tmp_path) -> None:
    with pytest.raises(IntegrityError):
        ensure_training_ready(tmp_path / "does-not-exist")
