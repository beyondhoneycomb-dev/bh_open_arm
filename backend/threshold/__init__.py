"""WP-2C-04 — collision-detection threshold modes + confirm/hysteresis (FR-SAF-014/021/022).

The machinery that turns a per-joint GMO residual into a debounced collision verdict, and the
precondition that governs when it may arm. Detection stays disabled by default across this band
(plan 02b §3.0); this package builds and validates the machinery offline, and the on-hardware
threshold calibration and reaction timing are deferred to WP-2C-03/06.

Public surface:

* `ThresholdCalibration` — the consumed WP-2C-03 base threshold thr0 [Nm], validated to the
  [10 x LSB, effort] contract band; `literature_default()` is the FR-SAF-020 starting point.
* `ThresholdMode` / `ThresholdConfig` — the STATIC / VELOCITY_SCALED / TRAJECTORY_SCHEDULED
  selection plus the optional accel term, confirm_samples, hysteresis, and per-joint enable;
  `ThresholdConfig.default()` is the spec 12 §2.12 [A] default.
* `effective_thresholds` / `build_schedule` / `ThresholdSchedule` — evaluate the per-joint
  threshold for one live sample, or pre-compute the scheduled profile from a planned trajectory.
* `ConfirmHysteresisGate` / `GateUpdate` — the per-joint two-sided debounce (consecutive-sample
  confirm, hysteresis-band release) that keeps the confirmed signal from chattering.
* `AccelLimitStatus` / `AccelLimitPolicy` / `ActivationDecision` /
  `check_acceleration_limit_precondition` — the FR-SAF-014 gate that refuses (or warns on) arming
  detection while joint acceleration limits are off.
* `ThresholdError` / `ThresholdConfigError` / `AccelerationLimitError` — the refusal hierarchy.
"""

from __future__ import annotations

from backend.threshold.activation import (
    AccelLimitPolicy,
    AccelLimitStatus,
    ActivationDecision,
    check_acceleration_limit_precondition,
)
from backend.threshold.calibration import ThresholdCalibration
from backend.threshold.confirm import ConfirmHysteresisGate, GateUpdate
from backend.threshold.errors import (
    AccelerationLimitError,
    ThresholdConfigError,
    ThresholdError,
)
from backend.threshold.modes import (
    ThresholdConfig,
    ThresholdMode,
    ThresholdSchedule,
    build_schedule,
    effective_thresholds,
)

__all__ = [
    "AccelLimitPolicy",
    "AccelLimitStatus",
    "AccelerationLimitError",
    "ActivationDecision",
    "ConfirmHysteresisGate",
    "GateUpdate",
    "ThresholdCalibration",
    "ThresholdConfig",
    "ThresholdConfigError",
    "ThresholdError",
    "ThresholdMode",
    "ThresholdSchedule",
    "build_schedule",
    "check_acceleration_limit_precondition",
    "effective_thresholds",
]
