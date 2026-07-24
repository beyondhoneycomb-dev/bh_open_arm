"""CG-4A-05b — a lineage record is immutable; a post-hoc edit is refused.

Two layers make it immutable: the record is a frozen dataclass, so an in-memory
field cannot be reassigned, and the store refuses a second write for a checkpoint
whose lineage is already recorded, so it cannot be overwritten on disk.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.training.lineage import (
    CheckpointId,
    TrainingLineageError,
    TrainingLineageStore,
)
from tests.wp4a05.support import fixture_record


def test_record_is_a_frozen_dataclass() -> None:
    """A field of a stored record cannot be reassigned in memory."""
    record = fixture_record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.pins.code_sha = "tampered"  # type: ignore[misc]


def test_re_recording_a_checkpoint_is_refused(tmp_path) -> None:
    """A second write for the same checkpoint identity is refused (immutable)."""
    checkpoint = CheckpointId("/runs/act", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, "content-hash")
        with pytest.raises(TrainingLineageError):
            store.record(fixture_record(revision="rev-9999"), checkpoint, "content-hash")


def test_snapshot_read_back_does_not_expose_the_stored_object(tmp_path) -> None:
    """Editing a read-back record cannot change what the store holds."""
    checkpoint = CheckpointId("/runs/act", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, "content-hash")
        first = store.snapshot_of(checkpoint)
        assert first is not None
        mutated = dataclasses.replace(first, train_config={"tampered": True})
        again = store.snapshot_of(checkpoint)
    assert again is not None
    assert again.train_config != mutated.train_config
    assert again.train_config == fixture_record().train_config


def test_a_reopened_store_still_refuses_the_edit(tmp_path) -> None:
    """Immutability survives a close/reopen: the disk record still cannot be rewritten."""
    checkpoint = CheckpointId("/runs/act", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, "content-hash")
    with TrainingLineageStore(tmp_path) as reopened, pytest.raises(TrainingLineageError):
        reopened.record(fixture_record(revision="rev-2"), checkpoint, "content-hash")
