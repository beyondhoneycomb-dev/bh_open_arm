"""WP-3D-04: the dataset-source identity reuses the recorder's `repo_id` rules.

Lineage tracks training inputs, so its dataset name must be a recorder-produced
stamped `repo_id` and never an `eval_` dataset. These tests hold that the reuse is
live — the `eval_` refusal is the recorder's own, and the stamp check accepts a
`repo_id` produced by the recorder's `stamp_repo_id` and rejects an unstamped one.
"""

from __future__ import annotations

import pytest

from backend.dataset.lineage import (
    LineageSourceError,
    is_stamped_repo_id,
    validate_dataset_repo_id,
)
from backend.recorder.embed import stamp_repo_id
from tests.wp3d04._support import fixture_repo_id


def test_a_recorder_stamped_repo_id_is_accepted() -> None:
    validate_dataset_repo_id(fixture_repo_id())
    assert is_stamped_repo_id(fixture_repo_id())


def test_an_eval_dataset_name_is_refused() -> None:
    eval_name = stamp_repo_id("openarm/eval_rollout")
    with pytest.raises(LineageSourceError):
        validate_dataset_repo_id(eval_name)


def test_an_unstamped_repo_id_is_refused() -> None:
    assert not is_stamped_repo_id("openarm/pick_place")
    with pytest.raises(LineageSourceError, match="stamp"):
        validate_dataset_repo_id("openarm/pick_place")


def test_a_repo_id_with_a_non_date_tail_is_not_stamped() -> None:
    assert not is_stamped_repo_id("openarm/pick_place_notadate")
    assert not is_stamped_repo_id("openarm/pick_place_20261301_100000")
