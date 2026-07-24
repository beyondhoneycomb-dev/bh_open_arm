"""WP-3D-04 ②: every required record field is present, and a hole is refused.

A record missing any required field, or carrying an empty episode mapping, is a
lineage hole the reverse query can never fill — `FAIL_BLOCKING`. These tests hold
that the store refuses each such record rather than storing a half-truth.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.dataset.lineage import LineageError, LineageRecord, LineageStore
from backend.dataset.lineage.constants import MEMORY_DATABASE, REQUIRED_RECORD_FIELDS
from tests.wp3d04._support import fixture_record


def test_a_complete_record_stores() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        run_id = store.record(fixture_record((0, 1, 2), "/runs/a", 1000))
        assert run_id > 0


def test_the_required_field_set_covers_every_dataclass_field() -> None:
    record_fields = {field.name for field in dataclasses.fields(LineageRecord)}
    assert set(REQUIRED_RECORD_FIELDS) == record_fields


@pytest.mark.parametrize(
    "field", ["repo_id", "dataset_content_hash", "revision", "stats_hash", "output_dir"]
)
def test_an_empty_string_field_is_refused(field: str) -> None:
    record = dataclasses.replace(fixture_record((0,), "/runs/a", 1000), **{field: "   "})
    with LineageStore(MEMORY_DATABASE) as store, pytest.raises(LineageError):
        store.record(record)


def test_an_empty_episode_mapping_is_fail_blocking() -> None:
    record = fixture_record((), "/runs/a", 1000)
    with (
        LineageStore(MEMORY_DATABASE) as store,
        pytest.raises(LineageError, match="episodes is empty"),
    ):
        store.record(record)


def test_a_non_positive_state_dim_is_refused() -> None:
    record = dataclasses.replace(fixture_record((0,), "/runs/a", 1000), state_dim=0)
    with LineageStore(MEMORY_DATABASE) as store, pytest.raises(LineageError):
        store.record(record)


def test_a_negative_step_is_refused() -> None:
    record = dataclasses.replace(fixture_record((0,), "/runs/a", 1000), step=-1)
    with LineageStore(MEMORY_DATABASE) as store, pytest.raises(LineageError):
        store.record(record)


def test_unsorted_or_duplicate_episodes_are_refused() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        with pytest.raises(LineageError, match="ascending"):
            store.record(fixture_record((2, 1), "/runs/a", 1000))
        with pytest.raises(LineageError, match="ascending"):
            store.record(fixture_record((1, 1), "/runs/b", 1000))


def test_a_negative_episode_index_is_refused() -> None:
    record = dataclasses.replace(fixture_record((0,), "/runs/a", 1000), episodes=(-1, 0))
    with LineageStore(MEMORY_DATABASE) as store, pytest.raises(LineageError):
        store.record(record)


def test_a_duplicate_checkpoint_identity_is_refused() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        store.record(fixture_record((0,), "/runs/a", 1000))
        with pytest.raises(LineageError, match="immutable"):
            store.record(fixture_record((1,), "/runs/a", 1000))
