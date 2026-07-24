"""The aborted-edit EDIT_INVALID marker makes an otherwise-whole dataset INVALID.

WP-3D-02/06 write `meta/EDIT_INVALID.json` when a sidecar remap fails its content
cross-check; the dataset stays structurally complete but its labels point at the
wrong episodes. This pins that the marker is honoured — a dataset wearing it is
INVALID and `ensure_training_ready` refuses it — so the sentinel is load-bearing,
not write-only. The isolation assertion is the teeth: only the marker check may
fire, because the tree is otherwise a valid READY dataset.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from backend.dataset.edit.constants import INVALID_MARKER_NAME
from backend.dataset.integrity import (
    CHECK_NO_EDIT_MARKER,
    VERDICT_INVALID,
    VERDICT_READY,
    IntegrityError,
    ensure_training_ready,
    verify_dataset,
)
from tests.wp3d05.materialize import MaterializedDataset


def _write_marker(dataset: MaterializedDataset) -> None:
    """Write the aborted-edit marker into an otherwise-READY dataset."""
    marker = dataset.root / INVALID_MARKER_NAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"reason": "sidecar remap cross-check failed"}), encoding="utf-8")


def test_marker_flips_a_ready_dataset_to_invalid(
    fresh_dataset: Callable[[], MaterializedDataset],
) -> None:
    dataset = fresh_dataset()
    assert verify_dataset(dataset.root).verdict == VERDICT_READY  # whole before the marker

    _write_marker(dataset)

    report = verify_dataset(dataset.root)
    assert report.verdict == VERDICT_INVALID
    fired = {result.name for result in report.failures}
    assert fired == {CHECK_NO_EDIT_MARKER}  # only the marker check bit; the tree is otherwise whole


def test_ensure_training_ready_refuses_a_marked_dataset(
    fresh_dataset: Callable[[], MaterializedDataset],
) -> None:
    dataset = fresh_dataset()
    _write_marker(dataset)
    with pytest.raises(IntegrityError):
        ensure_training_ready(dataset.root)
