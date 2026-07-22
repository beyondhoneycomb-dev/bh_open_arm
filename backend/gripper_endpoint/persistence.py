"""Atomic persistence for the gripper sign-mirror record (acceptance (1)).

The record is the disk source of truth for the cross-arm gripper mapping, so a torn
write is a corrupt SoT. The write is persist-then-swap — write a sibling temp file,
flush and `fsync` it, then `os.replace` onto the target, then `fsync` the parent
directory — which is POSIX-atomic: a reader sees either the whole previous file or
the whole new one, never a partial write, even across a mid-write kill.

This is the same discipline `backend.calibration.atomic_io` uses for the per-arm zero
calibration. That module's writer is bound to the `OpenArmCalibration` shape and its
frozen JSON Schema, so it cannot persist this different, cross-arm record; the
discipline is reused, the schema-bound function is not.

Loading validates before returning, so a config that violates the sign-mirror
relation is refused at read time (acceptance (2)) rather than surfacing later as a
left gripper that silently never opens (FR-MAN-017, FR-TEL-059).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from backend.gripper_endpoint.constants import RECORD_SUFFIX
from backend.gripper_endpoint.schema import GripperMirrorRecord


def gripper_record_path_for(directory: Path, robot_pair_id: str) -> Path:
    """Return the on-disk record path for an arm pair.

    Args:
        directory: The directory holding gripper records.
        robot_pair_id: The left/right arm-pair identifier.

    Returns:
        (Path) `<directory>/<robot_pair_id>.oa_gripper.json`.
    """
    return directory / f"{robot_pair_id}{RECORD_SUFFIX}"


def _utc_now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def save_gripper_record(path: Path, record: GripperMirrorRecord) -> GripperMirrorRecord:
    """Write a gripper record to disk atomically, stamping timestamps and checksum.

    Stamps `created_at` on first write and `last_updated_at` on every write, then does
    the temp-file / fsync / replace / fsync-dir swap. The record is re-validated as it
    is rebuilt from its own JSON, so a save can never persist a body that a load would
    then refuse.

    Args:
        path: Destination record path.
        record: The record to persist.

    Returns:
        (GripperMirrorRecord) The record as written (timestamps and checksum set).
    """
    now = _utc_now_iso()
    if record.created_at is None:
        record.created_at = now
    record.last_updated_at = now

    payload = record.to_json_dict()
    body = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)  # noqa: PTH105 — atomic rename primitive; Path.replace only wraps it
        _fsync_dir(path.parent)
    except BaseException:
        # A failed write must not leave a stray temp file a later glob would pick up.
        tmp_path.unlink(missing_ok=True)
        raise
    return GripperMirrorRecord.from_json_dict(payload)


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it is durable across a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_gripper_record(path: Path) -> GripperMirrorRecord:
    """Read, validate, and return a gripper record.

    Args:
        path: The record file path.

    Returns:
        (GripperMirrorRecord) The validated record.

    Raises:
        FileNotFoundError: If the file does not exist.
        GripperConfigError: If the payload violates the frozen shape, the checksum,
            or the sign-mirror relation (the load refusal of acceptance (2)).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return GripperMirrorRecord.from_json_dict(data)
