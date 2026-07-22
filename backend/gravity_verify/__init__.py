"""WP-2B-03 — v2 gravity-model verification on a static pose grid (FR-SAF-072, spec 12 §2.6).

This is PG-FRIC-001's *preceding evidence*, not a gate of its own: before the friction fit
(WP-2B-07) subtracts a gravity term, the WP-2B-02 model is checked against a measured torque
grid so a wrong gravity term cannot be absorbed into the friction parameters (spec 12 §2.6). It
consumes WP-2B-02's `select_backend`/`tau_grav` and WP-2B-01's joint layout by their declared
APIs; it computes no gravity of its own.

What runs on this host, on SYNTHETIC measurements or the committed v2 model:

* the residual harness — `compute_residuals` builds the whole-grid per-joint `tau_meas -
  tau_model` table (acceptance ①), and refuses the run when `use_velocity_and_torque=false`
  because there is then no measured torque (`VerificationConfig.require_torque_measurement`,
  FR-SAF-072, acceptance ③);
* the joint-2 fingerprint — `detect_j2_anomaly` flags a shoulder residual that reads as the
  un-applied `+pi/2` shift (acceptance ②), as two-sided logic, not a rubber stamp;
* the link7->EE quantifier — `quantify_link7_transfer` measures the relocated end-effector
  mass's share of each wrist joint's gravity, the wrist negative-branch input.

What is deferred (needs a torque-ON arm and an operator to align and hold each pose): the real
`tau_meas` grid. It is never fabricated — the synthetic generator is provisional by construction
and `reverify.reverify_from_fixture` re-runs the identical verification against a real capture
when one is supplied (THE ONE RULE — a synthetic run is never a real PG-FRIC-001 pass).
"""

from __future__ import annotations

from backend.gravity_verify.anomaly import J2AnomalyResult, detect_j2_anomaly
from backend.gravity_verify.config import VerificationConfig
from backend.gravity_verify.constants import (
    J2_ANOMALY_ABS_FLOOR_NM,
    J2_ANOMALY_RATIO,
    WRIST_DOMINANCE_FRACTION,
    WRIST_JOINT_INDICES,
)
from backend.gravity_verify.errors import GravityVerifyError, VerificationRefusedError
from backend.gravity_verify.harness import VerificationReport, run_verification
from backend.gravity_verify.link7 import (
    Link7TransferImpact,
    WristJointImpact,
    ee_dominated_wrist_joints,
    quantify_link7_transfer,
)
from backend.gravity_verify.measurement import (
    MeasurementBasis,
    PoseMeasurement,
    grid_basis,
    synthesize_measurements,
)
from backend.gravity_verify.residual import (
    JointResidual,
    JointResidualStats,
    PoseResidual,
    ResidualTable,
    compute_residuals,
    format_residual_table,
)

__all__ = [
    "J2_ANOMALY_ABS_FLOOR_NM",
    "J2_ANOMALY_RATIO",
    "WRIST_DOMINANCE_FRACTION",
    "WRIST_JOINT_INDICES",
    "GravityVerifyError",
    "J2AnomalyResult",
    "JointResidual",
    "JointResidualStats",
    "Link7TransferImpact",
    "MeasurementBasis",
    "PoseMeasurement",
    "PoseResidual",
    "ResidualTable",
    "VerificationConfig",
    "VerificationRefusedError",
    "VerificationReport",
    "WristJointImpact",
    "compute_residuals",
    "detect_j2_anomaly",
    "ee_dominated_wrist_joints",
    "format_residual_table",
    "grid_basis",
    "quantify_link7_transfer",
    "run_verification",
    "synthesize_measurements",
]
