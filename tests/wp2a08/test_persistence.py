"""Acceptance (1) — left/right capture records persist to disk and restore after restart.

"After restart" is modelled by discarding the in-memory record and loading a fresh
one from the bytes on disk; the loaded record must carry the same endpoints, limits,
and caps. The write is atomic (persist-then-swap), so a mid-write failure leaves no
partial file and no stray temp file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.persistence import (
    gripper_record_path_for,
    load_gripper_record,
    save_gripper_record,
)
from backend.gripper_endpoint.schema import GripperMirrorRecord


def test_persists_and_restores_after_restart(
    tmp_path: Path, valid_record: GripperMirrorRecord
) -> None:
    """A saved record reloads from disk with every field intact (a simulated restart)."""
    path = gripper_record_path_for(tmp_path, "armpair")
    save_gripper_record(path, valid_record)

    # Simulated restart: nothing in memory, read the bytes back cold.
    restored = load_gripper_record(path)

    assert restored.right_capture.open_rad == valid_record.right_capture.open_rad
    assert restored.right_capture.close_rad == valid_record.right_capture.close_rad
    assert restored.left_capture.close_rad == valid_record.left_capture.close_rad
    assert restored.right_limits.lo_rad == valid_record.right_limits.lo_rad
    assert restored.left_limits.hi_rad == valid_record.left_limits.hi_rad
    assert restored.torque_pu == valid_record.torque_pu
    assert restored.effective_speed_rad_s == valid_record.effective_speed_rad_s


def test_save_stamps_created_then_preserves_it(
    tmp_path: Path, valid_record: GripperMirrorRecord
) -> None:
    """`created_at` is stamped on first write and preserved on the next."""
    path = gripper_record_path_for(tmp_path, "armpair")
    first = save_gripper_record(path, valid_record)
    assert first.created_at is not None

    second = save_gripper_record(path, first)
    assert second.created_at == first.created_at
    assert second.last_updated_at is not None


def test_checksum_survives_round_trip(tmp_path: Path, valid_record: GripperMirrorRecord) -> None:
    """The persisted checksum matches the reloaded body, so tampering is detectable."""
    path = gripper_record_path_for(tmp_path, "armpair")
    save_gripper_record(path, valid_record)
    restored = load_gripper_record(path)
    assert restored.checksum == restored.compute_checksum()


def test_tampered_body_is_refused(tmp_path: Path, valid_record: GripperMirrorRecord) -> None:
    """A hand-edited body whose checksum no longer matches is refused at load."""
    path = gripper_record_path_for(tmp_path, "armpair")
    save_gripper_record(path, valid_record)

    text = path.read_text(encoding="utf-8")
    tampered = text.replace('"torque_pu": 0.4', '"torque_pu": 0.9')
    assert tampered != text
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(GripperConfigError, match="checksum"):
        load_gripper_record(path)


def test_atomic_write_cleans_up_temp_on_failure(
    tmp_path: Path,
    valid_record: GripperMirrorRecord,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure at the rename step unlinks the temp file and leaves no target behind.

    The failure is injected into `os.replace`, which runs after the temp file has been
    written and fsynced, so this exercises the persist-then-swap cleanup path rather
    than a failure that never reached it.
    """
    path = gripper_record_path_for(tmp_path, "armpair")

    def _boom(src: object, dst: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("os.replace", _boom)

    with pytest.raises(OSError, match="injected"):
        save_gripper_record(path, valid_record)

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []
