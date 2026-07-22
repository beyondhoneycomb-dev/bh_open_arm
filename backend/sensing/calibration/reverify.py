"""Real-fixture re-verification hook for the deferred capture (plan 02a §4.1).

Everything in WP-3B-13 runs offline except the *capture* itself: the five-method
hand-eye solve, the intrinsic solve, the store's staleness and collect-block, and
the YAML round-trip are all exercised on this host against synthetic
correspondences. What does not run here is the same math over a *real* capture — a
detected checkerboard/ChArUco on a real camera, real end-effector poses read from
the arm, an operator moving the board — because there is no camera, no board and no
operator on a desktop.

This hook is what that deferral ships. When a directory of real captures is supplied
(`OPENARM_CALIBRATION_REAL_FIXTURE`), `reverify_from_fixture` re-runs the *identical*
solvers — `calibrate_intrinsics` and `solve_hand_eye_all_methods` — over the real
bytes and returns records stamped `REAL_CAPTURE`. No solving path is re-implemented
for hardware; only the pose source changes. Until the fixture exists the bound test
skips with a reason, so no real intrinsic or extrinsic is ever asserted without the
capture that measured it.

Fixture directory layout (all optional except at least one of intrinsic/hand-eye):

- `binding.json`   — `{slot: {camera_serial, mount_id}}` for the record's key,
- `intrinsics.json` — `{slot: {object_points, image_points, image_size}}`,
- `hand_eye.json`  — `{slot: {setup, robot_poses, target_poses}}`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from backend.sensing.calibration.binding_key import CalibrationBindingKey
from backend.sensing.calibration.handeye import (
    HandEyeResult,
    HandEyeSetup,
    solve_hand_eye_all_methods,
)
from backend.sensing.calibration.intrinsics import CameraIntrinsics, calibrate_intrinsics
from backend.sensing.calibration.record import (
    CalibrationProvenance,
    CalibrationRecord,
    utc_now_iso,
)

FIXTURE_ENV_VAR = "OPENARM_CALIBRATION_REAL_FIXTURE"
BINDING_FILENAME = "binding.json"
INTRINSICS_FILENAME = "intrinsics.json"
HAND_EYE_FILENAME = "hand_eye.json"


@dataclass(frozen=True)
class CalibrationReverifyReport:
    """The records a real capture directory re-derived, one per slot.

    Attributes:
        records: The rebuilt calibration records, keyed by slot, each stamped
            `REAL_CAPTURE`.
    """

    records: dict[str, CalibrationRecord]


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _intrinsics_for(spec: dict[str, Any]) -> CameraIntrinsics:
    """Re-run the intrinsic solve over one slot's real board correspondences."""
    object_points = [np.asarray(view, dtype=np.float32) for view in spec["object_points"]]
    image_points = [np.asarray(view, dtype=np.float32) for view in spec["image_points"]]
    width, height = spec["image_size"]
    return calibrate_intrinsics(object_points, image_points, (int(width), int(height)))


def _hand_eye_for(spec: dict[str, Any]) -> HandEyeResult:
    """Re-run the five-method hand-eye solve over one slot's real poses."""
    setup = HandEyeSetup(spec["setup"])
    return solve_hand_eye_all_methods(spec["robot_poses"], spec["target_poses"], setup)


def reverify_from_fixture(fixture_dir: Path) -> CalibrationReverifyReport:
    """Re-run the calibration solvers against a directory of real captures.

    Args:
        fixture_dir: Directory of captured JSON (see the module docstring).

    Returns:
        (CalibrationReverifyReport) One `REAL_CAPTURE` record per slot present.

    Raises:
        FileNotFoundError: If neither an intrinsic nor a hand-eye capture is present.
    """
    intrinsics_path = fixture_dir / INTRINSICS_FILENAME
    hand_eye_path = fixture_dir / HAND_EYE_FILENAME
    if not intrinsics_path.is_file() and not hand_eye_path.is_file():
        raise FileNotFoundError(
            f"{fixture_dir} holds neither {INTRINSICS_FILENAME} nor {HAND_EYE_FILENAME}"
        )

    binding_path = fixture_dir / BINDING_FILENAME
    bindings = _load_json(binding_path) if binding_path.is_file() else {}

    intrinsics_by_slot = _load_json(intrinsics_path) if intrinsics_path.is_file() else {}
    hand_eye_by_slot = _load_json(hand_eye_path) if hand_eye_path.is_file() else {}

    records: dict[str, CalibrationRecord] = {}
    for slot_key in sorted(set(intrinsics_by_slot) | set(hand_eye_by_slot)):
        hand_eye = (
            _hand_eye_for(hand_eye_by_slot[slot_key]) if slot_key in hand_eye_by_slot else None
        )
        intrinsics = (
            _intrinsics_for(intrinsics_by_slot[slot_key])
            if slot_key in intrinsics_by_slot
            else None
        )
        binding = bindings.get(slot_key, {})
        binding_key = CalibrationBindingKey(
            camera_serial=str(binding.get("camera_serial", "")),
            slot_key=slot_key,
            mount_id=str(binding.get("mount_id", "")),
        )
        records[slot_key] = CalibrationRecord(
            performed_at=utc_now_iso(),
            binding_key=binding_key,
            sample_pose_count=hand_eye.sample_pose_count if hand_eye is not None else 0,
            provenance=CalibrationProvenance.REAL_CAPTURE,
            hand_eye=hand_eye,
            intrinsics=intrinsics,
        )
    return CalibrationReverifyReport(records=records)
