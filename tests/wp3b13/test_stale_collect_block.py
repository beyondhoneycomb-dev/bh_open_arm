"""Acceptance ③ — serial/slot/mount change auto-stales and blocks collection.

`02b` WP-3B-13 ③ and `06` FR-CAM-028: a calibration is valid only for the rigid
relationship it was captured under. A serial swap, slot reassignment or mount
reattach makes it stale, and a stale or missing calibration blocks the start of
collection. The negative branch is `FAIL_BLOCKING` — a stale calibration allowed to
collect is a defect — so the block raises rather than returning a flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.sensing.calibration import (
    CalibrationBindingKey,
    CalibrationProvenance,
    CalibrationRecord,
    CalibrationStatus,
    CalibrationStore,
    MissingCalibrationError,
    StaleCalibrationError,
    is_stale,
)


def _record(serial: str, slot: str, mount: str) -> CalibrationRecord:
    """A minimal record bound to a given (serial, slot, mount) key."""
    return CalibrationRecord(
        performed_at="2026-07-22T00:00:00+00:00",
        binding_key=CalibrationBindingKey(camera_serial=serial, slot_key=slot, mount_id=mount),
        sample_pose_count=12,
        provenance=CalibrationProvenance.SYNTHETIC,
        hand_eye=None,
        intrinsics=None,
    )


def test_binding_key_detects_each_change_trigger() -> None:
    """Each of serial, slot and mount changing is reported individually."""
    base = CalibrationBindingKey(camera_serial="A", slot_key="front", mount_id="m1")

    assert base.changed_fields(base) == ()
    assert base.changed_fields(CalibrationBindingKey("B", "front", "m1")) == ("camera_serial",)
    assert base.changed_fields(CalibrationBindingKey("A", "wrist", "m1")) == ("slot_key",)
    assert base.changed_fields(CalibrationBindingKey("A", "front", "m2")) == ("mount_id",)


def test_valid_calibration_permits_collection_start(tmp_path: Path) -> None:
    """A record whose binding matches the live key is VALID and does not block."""
    store = CalibrationStore(directory=tmp_path)
    key = CalibrationBindingKey("A", "front", "m1")
    store.save(_record("A", "front", "m1"))

    assert store.status("front", key) is CalibrationStatus.VALID
    store.assert_collection_startable({"front": key})  # does not raise


def test_serial_change_stales_and_blocks(tmp_path: Path) -> None:
    """A camera swap under the same slot stales the calibration and blocks start."""
    store = CalibrationStore(directory=tmp_path)
    store.save(_record("A", "front", "m1"))
    live = CalibrationBindingKey("B", "front", "m1")

    assert store.status("front", live) is CalibrationStatus.STALE
    with pytest.raises(StaleCalibrationError):
        store.assert_collection_startable({"front": live})


def test_mount_change_stales_and_blocks(tmp_path: Path) -> None:
    """A remount under the same slot and serial stales the calibration and blocks."""
    store = CalibrationStore(directory=tmp_path)
    store.save(_record("A", "front", "m1"))
    live = CalibrationBindingKey("A", "front", "m2")

    assert store.status("front", live) is CalibrationStatus.STALE
    with pytest.raises(StaleCalibrationError):
        store.assert_collection_startable({"front": live})


def test_slot_reassignment_leaves_new_slot_uncalibrated(tmp_path: Path) -> None:
    """Moving a camera to a new slot leaves that slot MISSING, which blocks start."""
    store = CalibrationStore(directory=tmp_path)
    store.save(_record("A", "front", "m1"))
    live = CalibrationBindingKey("A", "wrist", "m1")

    assert store.status("wrist", live) is CalibrationStatus.MISSING
    with pytest.raises(MissingCalibrationError):
        store.assert_collection_startable({"wrist": live})


def test_missing_calibration_blocks_collection_start(tmp_path: Path) -> None:
    """A slot with no calibration at all blocks collection (no factory fallback)."""
    store = CalibrationStore(directory=tmp_path)
    live = CalibrationBindingKey("A", "front", "m1")

    assert store.status("front", live) is CalibrationStatus.MISSING
    with pytest.raises(MissingCalibrationError):
        store.assert_collection_startable({"front": live})


def test_collection_block_scans_all_slots(tmp_path: Path) -> None:
    """One stale slot among several valid ones still blocks the whole start."""
    store = CalibrationStore(directory=tmp_path)
    store.save(_record("A", "front", "m1"))
    store.save(_record("B", "wrist", "m1"))
    live = {
        "front": CalibrationBindingKey("A", "front", "m1"),
        "wrist": CalibrationBindingKey("B", "wrist", "m9"),  # remounted
    }

    with pytest.raises(StaleCalibrationError):
        store.assert_collection_startable(live)


def test_is_stale_helper_agrees_with_status(tmp_path: Path) -> None:
    """The `is_stale` helper matches the store's STALE verdict."""
    record = _record("A", "front", "m1")
    assert not is_stale(record, CalibrationBindingKey("A", "front", "m1"))
    assert is_stale(record, CalibrationBindingKey("A", "front", "m2"))
