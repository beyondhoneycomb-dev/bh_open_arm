"""OpenArm follower calibration: the frozen CTR-CAL@v1 schema and its atomic I/O.

`schema` is the CONTRACT_FROZEN shape of the on-disk calibration JSON (the disk SoT of
02 FR-CON-064 / 16 M-1); `atomic_io` is its only writer (persist-then-swap); `verify`
is the zero-residual check the set-zero flow and the power-cycle re-verify both run.
"""

from __future__ import annotations

from backend.calibration.atomic_io import (
    CALIBRATION_SUFFIX,
    calibration_path_for,
    load_calibration,
    save_calibration_atomic,
)
from backend.calibration.schema import (
    CONTRACT_ID,
    MOTOR_COUNT,
    MOTOR_ORDER,
    SCHEMA_VERSION,
    ZERO_RESIDUAL_TOLERANCE_DEG,
    CalibrationError,
    OpenArmCalibration,
    ZeroMethod,
)
from backend.calibration.verify import ResidualResult, compute_residual

__all__ = [
    "CALIBRATION_SUFFIX",
    "CONTRACT_ID",
    "MOTOR_COUNT",
    "MOTOR_ORDER",
    "SCHEMA_VERSION",
    "ZERO_RESIDUAL_TOLERANCE_DEG",
    "CalibrationError",
    "OpenArmCalibration",
    "ResidualResult",
    "ZeroMethod",
    "calibration_path_for",
    "compute_residual",
    "load_calibration",
    "save_calibration_atomic",
]
