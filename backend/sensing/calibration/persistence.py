"""Atomic YAML persistence for calibration records (WP-3B-13, FR-CAM-027).

A calibration record is the disk source of truth for a camera's extrinsic and
intrinsic, so a torn write is a corrupt source. The write is persist-then-swap —
temp file, flush, `fsync`, `os.replace`, then `fsync` the parent directory — which
is POSIX-atomic: a reader sees either the whole prior file or the whole new one.

This is the same discipline `backend.gripper_endpoint.persistence` and
`backend.calibration.atomic_io` use; the discipline is reused, not the schema-bound
writer, because those persist different records.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from backend.sensing.calibration.constants import CALIBRATION_FILE_SUFFIX
from backend.sensing.calibration.record import CalibrationRecord, utc_now_iso


def calibration_path_for(directory: Path, slot_key: str) -> Path:
    """Return the on-disk record path for a camera slot.

    Args:
        directory: The directory holding calibration records.
        slot_key: The camera slot key.

    Returns:
        (Path) `<directory>/<slot_key>.oa_calibration.yaml`.
    """
    return directory / f"{slot_key}{CALIBRATION_FILE_SUFFIX}"


def save_calibration_record(path: Path, record: CalibrationRecord) -> CalibrationRecord:
    """Write a calibration record to disk atomically, stamping `performed_at`.

    The record is rebuilt from its own serialised body before return, so a save can
    never persist something a load would then refuse.

    Args:
        path: Destination record path.
        record: The record to persist. When its `performed_at` is empty it is
            stamped with the current UTC instant.

    Returns:
        (CalibrationRecord) The record as written.
    """
    stamped = record
    if not record.performed_at:
        stamped = _with_timestamp(record, utc_now_iso())

    payload = stamped.to_yaml_dict()
    body = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True, default_flow_style=False)

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
    return CalibrationRecord.from_yaml_dict(payload)


def load_calibration_record(path: Path) -> CalibrationRecord:
    """Read, validate and return a calibration record.

    Args:
        path: The record file path.

    Returns:
        (CalibrationRecord) The validated record.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CalibrationRecord.from_yaml_dict(data)


def _with_timestamp(record: CalibrationRecord, performed_at: str) -> CalibrationRecord:
    """Return a copy of the record with `performed_at` set."""
    from dataclasses import replace

    return replace(record, performed_at=performed_at)


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it is durable across a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
