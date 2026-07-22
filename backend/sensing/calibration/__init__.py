"""Camera calibration — intrinsic and five-method hand-eye (WP-3B-13).

`06` FR-CAM-023..028/030. The public surface:

* `calibrate_intrinsics` / `CameraIntrinsics` — the sole intrinsic source for a UVC
  webcam (no factory path), carrying the RMS reprojection error.
* `solve_hand_eye_all_methods` / `HandEyeResult` — the five methods computed
  simultaneously with their pairwise deviation; there is no single-method result.
* `CalibrationBindingKey`, `CalibrationRecord`, `CalibrationStore` — YAML-persisted
  records and the serial/slot/mount staleness gate that blocks collection start.
* `reverify_from_fixture` — the deferred real-capture re-verification hook.

The real capture (checkerboard, operator, real camera) is deferred; everything else
runs offline against `synthetic` inputs.
"""

from __future__ import annotations

from backend.sensing.calibration.binding_key import CalibrationBindingKey
from backend.sensing.calibration.errors import (
    CalibrationError,
    CalibrationInputError,
    CollectionBlockedError,
    MissingCalibrationError,
    StaleCalibrationError,
)
from backend.sensing.calibration.handeye import (
    HandEyeResult,
    HandEyeSetup,
    MethodDeviation,
    MethodSolution,
    solve_hand_eye_all_methods,
)
from backend.sensing.calibration.intrinsics import (
    CameraIntrinsics,
    IntrinsicSource,
    calibrate_intrinsics,
)
from backend.sensing.calibration.record import (
    CalibrationProvenance,
    CalibrationRecord,
    utc_now_iso,
)
from backend.sensing.calibration.reverify import (
    CalibrationReverifyReport,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.sensing.calibration.store import (
    CalibrationStatus,
    CalibrationStore,
    is_stale,
)

__all__ = [
    "CalibrationBindingKey",
    "CalibrationError",
    "CalibrationInputError",
    "CalibrationProvenance",
    "CalibrationRecord",
    "CalibrationReverifyReport",
    "CalibrationStatus",
    "CalibrationStore",
    "CameraIntrinsics",
    "CollectionBlockedError",
    "HandEyeResult",
    "HandEyeSetup",
    "IntrinsicSource",
    "MethodDeviation",
    "MethodSolution",
    "MissingCalibrationError",
    "StaleCalibrationError",
    "calibrate_intrinsics",
    "fixture_dir_from_env",
    "is_stale",
    "reverify_from_fixture",
    "solve_hand_eye_all_methods",
    "utc_now_iso",
]
