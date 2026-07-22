"""The calibration store: lookup, staleness, and the collect-block (WP-3B-13).

`06` FR-CAM-028 is the reason this module exists. A calibration is valid only for
the rigid relationship it was captured under, so on any serial/slot/mount change
the stored calibration is *stale*, and a stale (or missing) calibration must
*block the start of collection*. `assert_collection_startable` is that block: it
raises rather than returning, because `06`'s negative branch makes "stale state
allowed to collect" a `FAIL_BLOCKING` defect — a block that can be caught and
stepped past is not a block.

The store is disk-backed: records live as one YAML per slot (`persistence`), and a
lookup reads the current file so a re-calibration on disk is seen without a reload
step.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.sensing.calibration.binding_key import CalibrationBindingKey
from backend.sensing.calibration.errors import MissingCalibrationError, StaleCalibrationError
from backend.sensing.calibration.persistence import (
    calibration_path_for,
    load_calibration_record,
    save_calibration_record,
)
from backend.sensing.calibration.record import CalibrationRecord


class CalibrationStatus(Enum):
    """A slot's calibration status against the live binding key.

    `MISSING` — no record on disk. `STALE` — a record exists but under a different
    serial/slot/mount. `VALID` — a record whose binding key matches the live one.
    Only `VALID` permits collection to start (FR-CAM-028); `06` FR-CAM-061 renders
    these as the per-slot badge.
    """

    VALID = "valid"
    STALE = "stale"
    MISSING = "missing"


def is_stale(record: CalibrationRecord, current_key: CalibrationBindingKey) -> bool:
    """Whether a stored record's binding no longer matches the live one.

    Args:
        record: The stored calibration.
        current_key: The camera's current (serial, slot, mount) binding.

    Returns:
        (bool) True when any of serial/slot/mount differs.
    """
    return bool(record.binding_key.changed_fields(current_key))


@dataclass
class CalibrationStore:
    """A directory of per-slot calibration records with the FR-CAM-028 gate.

    Ownership: one store instance is the authority for one collection session's
    calibrations, reading and writing under a single directory. It holds no cache —
    every query reads the current file, so a calibration written by another process
    is seen on the next lookup.

    Attributes:
        directory: The directory holding `<slot>.oa_calibration.yaml` records.
    """

    directory: Path

    def lookup(self, slot_key: str) -> CalibrationRecord | None:
        """Return the stored calibration for a slot, or None when absent.

        Args:
            slot_key: The camera slot key.

        Returns:
            (CalibrationRecord | None) The record, or None if no file exists.
        """
        path = calibration_path_for(self.directory, slot_key)
        if not path.is_file():
            return None
        return load_calibration_record(path)

    def save(self, record: CalibrationRecord) -> CalibrationRecord:
        """Persist a calibration record for its slot.

        Args:
            record: The record to store.

        Returns:
            (CalibrationRecord) The record as written.
        """
        path = calibration_path_for(self.directory, record.slot_key)
        return save_calibration_record(path, record)

    def status(self, slot_key: str, current_key: CalibrationBindingKey) -> CalibrationStatus:
        """Return a slot's calibration status against the live binding key.

        Args:
            slot_key: The camera slot key.
            current_key: The camera's current binding.

        Returns:
            (CalibrationStatus) MISSING, STALE or VALID.
        """
        record = self.lookup(slot_key)
        if record is None:
            return CalibrationStatus.MISSING
        return CalibrationStatus.STALE if is_stale(record, current_key) else CalibrationStatus.VALID

    def assert_collection_startable(
        self, current_keys: Mapping[str, CalibrationBindingKey]
    ) -> None:
        """Block collection start unless every camera has a valid calibration.

        `06` FR-CAM-028: a stale or missing calibration blocks the start of data
        collection. This raises on the first offending slot; a caller that catches
        it and proceeds is the `FAIL_BLOCKING` violation the acceptance forbids.

        Args:
            current_keys: The live binding key for each camera slot that must be
                calibrated before collection.

        Raises:
            MissingCalibrationError: If any slot has no stored calibration.
            StaleCalibrationError: If any slot's calibration is stale.
        """
        for slot_key in sorted(current_keys):
            current_key = current_keys[slot_key]
            record = self.lookup(slot_key)
            if record is None:
                raise MissingCalibrationError(
                    f"slot {slot_key!r} has no calibration; a UVC webcam has no factory "
                    "intrinsic source, so collection start is blocked (FR-CAM-023/028)"
                )
            changed = record.binding_key.changed_fields(current_key)
            if changed:
                raise StaleCalibrationError(
                    f"slot {slot_key!r} calibration is stale: {', '.join(changed)} changed since "
                    "it was captured; recalibrate before starting collection (FR-CAM-028)"
                )
