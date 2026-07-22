"""WP-2C-03 — the collision-threshold calibration wizard.

`12` FR-SAF-060 makes the operating collision threshold a *calibration output*, not a fixed
constant: a representative trajectory is run repeatedly in a collision-free state, the
per-joint residual max and sigma are collected, and a threshold is proposed by `max + 3sigma`
or by 105-110 % of the residual maximum. Everything that is arithmetic runs on this host and
genuinely passes:

  * the per-joint residual max/sigma collector across repeated runs (`collector`).
  * the two `12` FR-SAF-060 proposal rules, each bounded below by the ten-LSB physics floor
    and above by the URDF effort cap (`proposer`) — both bounds imported from WP-1-06, never
    re-derived (`12` FR-SAF-019).
  * the `12` FR-SAF-063 sensitivity presets over a calibrated base and their effective
    per-joint Nm display (`presets`).
  * the per-joint effective-threshold display that shows the calibrated result beside the
    `12` FR-SAF-020 literature default and its "NOT an OpenArm-measured value" label, also
    imported from WP-1-06 (`wizard`).
  * the synthetic collision-free residual stream that proves the math against a known
    envelope (`synthetic`).

What does not run here is the calibration *run* itself — a real collision-free trajectory
under WP-2C-01's live residual with an operator attesting no contact. It is deferred to a
real fixture and re-run by `reverify.reverify_from_fixture`; a proposal built from synthetic
residuals is explicitly non-canonical, and `wizard.require_canonical` refuses to present it
as the operating threshold, because a measured-threshold green with no measurement is the
safety lie THE ONE RULE forbids.
"""

from __future__ import annotations

from backend.threshold_calib.collector import (
    CollectorError,
    ResidualCollector,
    ResidualStats,
    collector_for_arm,
)
from backend.threshold_calib.constants import (
    FIXTURE_ENV_VAR,
    METHOD_MAX_PLUS_SIGMA,
    METHOD_NOMINAL_SCALED,
    NOMINAL_SCALE_DEFAULT,
    NOMINAL_SCALE_MAX,
    NOMINAL_SCALE_MIN,
    PROVENANCE_REAL_ATTESTED,
    PROVENANCE_SYNTHETIC,
    SENSITIVITY_PRESETS,
    SIGMA_MULTIPLE,
    SensitivityPreset,
)
from backend.threshold_calib.presets import (
    EffectiveThreshold,
    PresetApplication,
    PresetError,
    apply_preset,
)
from backend.threshold_calib.proposer import (
    PerJointThreshold,
    ProposalError,
    ThresholdProposal,
    propose_max_plus_sigma,
    propose_nominal_scaled,
)
from backend.threshold_calib.reverify import (
    RealCalibrationVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.threshold_calib.synthetic import (
    SyntheticTruth,
    synthetic_residual_run,
    synthetic_truth,
)
from backend.threshold_calib.wizard import (
    Calibration,
    CalibrationNotCanonicalError,
    JointDisplayRow,
    NoCollisionJudgment,
    ThresholdDisplay,
    attested_calibration,
    effective_threshold_display,
    synthetic_calibration,
)

__all__ = [
    "FIXTURE_ENV_VAR",
    "METHOD_MAX_PLUS_SIGMA",
    "METHOD_NOMINAL_SCALED",
    "NOMINAL_SCALE_DEFAULT",
    "NOMINAL_SCALE_MAX",
    "NOMINAL_SCALE_MIN",
    "PROVENANCE_REAL_ATTESTED",
    "PROVENANCE_SYNTHETIC",
    "SENSITIVITY_PRESETS",
    "SIGMA_MULTIPLE",
    "Calibration",
    "CalibrationNotCanonicalError",
    "CollectorError",
    "EffectiveThreshold",
    "JointDisplayRow",
    "NoCollisionJudgment",
    "PerJointThreshold",
    "PresetApplication",
    "PresetError",
    "ProposalError",
    "RealCalibrationVerification",
    "ResidualCollector",
    "ResidualStats",
    "SensitivityPreset",
    "SyntheticTruth",
    "ThresholdDisplay",
    "ThresholdProposal",
    "apply_preset",
    "attested_calibration",
    "collector_for_arm",
    "effective_threshold_display",
    "fixture_dir_from_env",
    "propose_max_plus_sigma",
    "propose_nominal_scaled",
    "reverify_from_fixture",
    "synthetic_calibration",
    "synthetic_residual_run",
    "synthetic_truth",
]
