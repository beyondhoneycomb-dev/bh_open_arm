"""CG-4A-05a — all eight `FR-TRN-054` elements present, a missing one BLOCKs.

The acceptance is binary: a fixture training's lineage carries (a)-(h) in full, and
removing any one is refused. The (g) container element is the load-bearing negative
branch — not-used is a recorded value, an absent field is a block.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.training.lineage import (
    CONTAINER_NOT_USED,
    CheckpointId,
    LineageRecordError,
    TrainingLineageStore,
    VersionPins,
)
from tests.wp4a05.support import fixture_observation, fixture_record


def test_full_fixture_record_has_all_eight_elements() -> None:
    """A record built from the fixture validates — all eight elements present."""
    record = fixture_record()
    record.validate()  # does not raise
    serialised = record.to_dict()
    for key in (
        "dataset",
        "observation",
        "merge_history",
        "train_config",
        "code_sha",
        "lerobot_version",
        "container_digest",
        "degenerate_decisions",
    ):
        assert key in serialised, f"element {key} absent from serialised record"


def test_missing_dataset_stats_hash_blocks() -> None:
    """Element (a): an empty stats hash is a blocking hole."""
    record = fixture_record()
    holed = dataclasses.replace(record, dataset=dataclasses.replace(record.dataset, stats_hash=""))
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_missing_dataset_repo_id_blocks() -> None:
    """Element (a): an empty repo_id is a blocking hole."""
    record = fixture_record()
    holed = dataclasses.replace(record, dataset=dataclasses.replace(record.dataset, repo_id="  "))
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_empty_observation_names_blocks() -> None:
    """Element (b): an observation with no channel names cannot reproduce the state."""
    record = fixture_record()
    holed = dataclasses.replace(
        record, observation=dataclasses.replace(record.observation, names=())
    )
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_observation_names_count_must_match_state_shape() -> None:
    """Element (b): a names/width mismatch is refused — the state is not reproducible."""
    record = fixture_record()
    truncated = record.observation.names[:-1]
    holed = dataclasses.replace(
        record, observation=dataclasses.replace(record.observation, names=truncated)
    )
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_empty_merge_history_blocks() -> None:
    """Element (c): a run with no source session has no episodes to attribute."""
    record = fixture_record()
    holed = dataclasses.replace(record, merge_history=())
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_empty_train_config_blocks() -> None:
    """Element (d): the full config is what makes the run reproducible."""
    record = fixture_record()
    holed = dataclasses.replace(record, train_config={})
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_blank_code_sha_blocks() -> None:
    """Element (e): a blank training-code SHA is a hole."""
    record = fixture_record()
    holed = dataclasses.replace(record, pins=dataclasses.replace(record.pins, code_sha="  "))
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_blank_lerobot_version_blocks() -> None:
    """Element (f): a blank LeRobot version is a hole."""
    record = fixture_record()
    holed = dataclasses.replace(record, pins=dataclasses.replace(record.pins, lerobot_version=""))
    with pytest.raises(LineageRecordError):
        holed.validate()


def test_none_degenerate_decisions_blocks_but_empty_is_present() -> None:
    """Element (h): absent (None) BLOCKs, but an empty tuple is a present element."""
    record = fixture_record()
    absent = dataclasses.replace(record, degenerate_decisions=None)
    with pytest.raises(LineageRecordError):
        absent.validate()
    # Empty is a positive statement — degeneracy checked, none found — not a hole.
    clean = fixture_record(degenerate_decisions=[])
    clean.validate()  # does not raise


def test_container_absent_field_blocks_but_not_used_value_passes() -> None:
    """Element (g): the `02c` §1.5 negative branch — absence != not-used.

    A blank container digest is an ABSENT field and BLOCKs; the explicit
    `CONTAINER_NOT_USED` value PASSES; a real digest PASSES.
    """
    absent = fixture_record(container_digest="")
    with pytest.raises(LineageRecordError):
        absent.validate()

    not_used = fixture_record(container_digest=CONTAINER_NOT_USED)
    not_used.validate()  # explicit value -> present -> passes

    adopted = fixture_record(container_digest="sha256:deadbeef")
    adopted.validate()  # a real digest -> passes


def test_store_refuses_to_write_a_holed_record(tmp_path) -> None:
    """The writer enforces presence: a holed record never reaches either store."""
    record = fixture_record()
    holed = dataclasses.replace(
        record, pins=VersionPins(code_sha="x", lerobot_version="0.6.0", container_digest="")
    )
    with TrainingLineageStore(tmp_path) as store:
        with pytest.raises(LineageRecordError):
            store.record(holed, CheckpointId("/runs/act", 1000), "content-hash")
        assert store.snapshot_of(CheckpointId("/runs/act", 1000)) is None


def test_container_not_used_survives_the_round_trip(tmp_path) -> None:
    """A recorded not-used container reads back as the explicit value, still present."""
    record = fixture_record(container_digest=CONTAINER_NOT_USED)
    checkpoint = CheckpointId("/runs/act", 2000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(record, checkpoint, "content-hash")
        restored = store.snapshot_of(checkpoint)
    assert restored is not None
    assert restored.pins.container_digest == CONTAINER_NOT_USED
    assert fixture_observation().names == restored.observation.names
