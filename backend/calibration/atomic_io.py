"""Atomic persistence for the OpenArm follower calibration JSON (16 M-1).

The disk JSON is the calibration source of truth (02 FR-CON-064), so a torn write is
a corrupt SoT. The write is persist-then-swap — write a sibling temp file, flush and
`fsync` it, then `os.replace` onto the target — which is POSIX-atomic: a reader of the
target path sees either the whole previous file or the whole new one, never a partial
write, even if the process is killed mid-write (acceptance ⑧). The parent directory is
fsynced after the rename so the swap itself survives a crash.

This module is the ONLY writer of the calibration file. Loading validates the payload
against the frozen `schema.json` before it is trusted, so a hand-edited or truncated
file is rejected at read time rather than surfacing as a wrong joint angle later.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from backend.calibration.schema import OpenArmCalibration

# The frozen JSON Schema sits next to this module; it is loaded once and reused so the
# validator and the frozen contract cannot drift.
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"

# The calibration file name suffix. It is distinct from LeRobot's own `<id>.json`
# MotorCalibration file so the two persistence mechanisms never read each other's
# bytes (the OpenArm zero lives in motor NV + this file, not in MotorCalibration).
CALIBRATION_SUFFIX = ".oa_cal.json"


def _load_schema() -> dict[str, Any]:
    """Load the frozen calibration JSON Schema."""
    schema: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


def calibration_path_for(calibration_dir: Path, robot_id: str) -> Path:
    """Return the calibration file path for a follower instance.

    Args:
        calibration_dir: The follower's calibration directory (LeRobot layout).
        robot_id: The follower instance id.

    Returns:
        (Path) `<calibration_dir>/<robot_id>.oa_cal.json`.
    """
    return calibration_dir / f"{robot_id}{CALIBRATION_SUFFIX}"


def _utc_now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def save_calibration_atomic(path: Path, calibration: OpenArmCalibration) -> OpenArmCalibration:
    """Write a calibration to disk atomically, stamping timestamps and checksum.

    Stamps `created_at` on first write and `last_updated_at` on every write, computes
    the checksum over the final body, validates the result against the frozen schema,
    then does the temp-file/fsync/replace swap.

    Args:
        path: Destination calibration file path.
        calibration: The calibration to persist.

    Returns:
        (OpenArmCalibration) The calibration as written (with timestamps and checksum).
    """
    now = _utc_now_iso()
    stamped = calibration
    if stamped.created_at is None:
        stamped.created_at = now
    stamped.last_updated_at = now

    payload = stamped.to_json_dict()
    jsonschema.validate(payload, _load_schema())
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
        # A failed write must not leave a stray temp file that a later glob picks up.
        tmp_path.unlink(missing_ok=True)
        raise
    return OpenArmCalibration.from_json_dict(payload)


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it is durable across a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_calibration(path: Path) -> OpenArmCalibration:
    """Read, schema-validate, and checksum-verify a calibration file.

    Args:
        path: The calibration file path.

    Returns:
        (OpenArmCalibration) The validated calibration.

    Raises:
        FileNotFoundError: If the file does not exist.
        CalibrationError: If the payload violates the frozen shape or checksum.
        jsonschema.ValidationError: If the payload violates the frozen JSON Schema.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(data, _load_schema())
    return OpenArmCalibration.from_json_dict(data)
