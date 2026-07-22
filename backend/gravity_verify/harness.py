"""The WP-2B-03 verification orchestrator: residual table, joint-2 fingerprint, link7 impact.

This assembles the three checks into one report and carries the WP-2B-03 contract on its face:
gravity-model verification is PG-FRIC-001's *preceding evidence*, not a gate of its own (spec 12
§2.6). A run is refused outright when torque measurement is unavailable (FR-SAF-072), and a run
built from synthetic measurements is marked provisional and ships a deferred manifest naming the
real torque-ON pose grid it still needs and the fixture hook that consumes it.

The report never renders a pass/fail verdict on a provisional (synthetic) basis. The residual
numbers, the anomaly ratio, and the link7 contribution are real computations; whether they clear
PG-FRIC-001's threshold is decided only once the real grid arrives through the re-verification
hook (THE ONE RULE — a synthetic-log run is never a real measured pass).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backend.gravity.selector import select_backend
from backend.gravity_verify.anomaly import J2AnomalyResult, detect_j2_anomaly
from backend.gravity_verify.config import VerificationConfig
from backend.gravity_verify.constants import WRIST_JOINT_INDICES
from backend.gravity_verify.link7 import (
    Link7TransferImpact,
    ee_dominated_wrist_joints,
    quantify_link7_transfer,
)
from backend.gravity_verify.measurement import MeasurementBasis, PoseMeasurement
from backend.gravity_verify.residual import ResidualTable, compute_residuals

WP_ID = "WP-2B-03"
# Recorded as the contract, never a gate id: this WP is preceding evidence for PG-FRIC-001.
PG_PRECEDING = "PG-FRIC-001"
# The re-verification hook and its fixture switch, named as strings so the report can advertise
# the deferral without this module importing the hook (which imports this one).
REVERIFICATION_HOOK = "backend.gravity_verify.reverify.reverify_from_fixture"
FIXTURE_ENV_VAR = "OPENARM_GRAVITY_VERIFY_REAL_FIXTURE"


@dataclass(frozen=True)
class VerificationReport:
    """The assembled WP-2B-03 evidence for one pose grid.

    Attributes:
        basis: The measurement basis the grid was on.
        provisional: True for a synthetic basis; a provisional report is never a PG-FRIC-001
            preceding pass.
        residual_table: The whole-grid per-joint residual table (①).
        j2_anomaly: The joint-2 +pi/2-shift fingerprint result (②).
        link7_impact: The relocated-EE-mass gravity contribution on the wrist joints, at the
            grid's worst wrist-residual pose.
    """

    basis: MeasurementBasis
    provisional: bool
    residual_table: ResidualTable
    j2_anomaly: J2AnomalyResult
    link7_impact: Link7TransferImpact

    def as_record(self) -> dict[str, Any]:
        """Render the report as a plain artifact mapping, deferral and contract included.

        Returns:
            (dict[str, Any]) The evidence, with the PG-FRIC-001-preceding contract note, the
            provisional flag, per-joint residual statistics, the anomaly verdict, the link7
            impact, and the deferred manifest.
        """
        return {
            "wp_id": WP_ID,
            "preceding_evidence_for": PG_PRECEDING,
            "contract_note": (
                "gravity-model verification is PG-FRIC-001 preceding evidence, not a separate "
                "gate (WP-2B-03, spec 12 §2.6)"
            ),
            "basis": self.basis.value,
            "provisional": self.provisional,
            "joint_residual_rms_nm": [stat.rms_nm for stat in self.residual_table.joint_stats],
            "joint_residual_max_abs_nm": [
                stat.max_abs_nm for stat in self.residual_table.joint_stats
            ],
            "j2_anomaly": {
                "joint2_rms_nm": self.j2_anomaly.joint2_rms_nm,
                "peer_median_rms_nm": self.j2_anomaly.peer_median_rms_nm,
                "ratio": self.j2_anomaly.ratio,
                "is_anomalous": self.j2_anomaly.is_anomalous,
            },
            "link7_transfer": {
                "relocated_mass_kg": self.link7_impact.relocated_mass_kg,
                "ee_dominated_wrist_joints": list(ee_dominated_wrist_joints(self.link7_impact)),
                "wrist_ee_fraction": [
                    joint.ee_fraction for joint in self.link7_impact.wrist_joints
                ],
            },
            "deferred": _deferred_manifest(self.basis),
        }


def run_verification(
    grid: Sequence[PoseMeasurement],
    config: VerificationConfig,
) -> VerificationReport:
    """Run the WP-2B-03 verification over one pose grid.

    Refuses when torque measurement is unavailable (FR-SAF-072), computes the residual table,
    runs the joint-2 fingerprint check, and quantifies the link7->EE impact at the grid's worst
    wrist-residual pose.

    Args:
        grid: The pose/measurement grid; all-real or all-synthetic.
        config: The run configuration; its torque-availability gate is checked first.

    Returns:
        (VerificationReport) The assembled evidence, provisional on a synthetic basis.

    Raises:
        VerificationRefusedError: If `config.use_velocity_and_torque` is False.
        GravityVerifyError: On an empty or mixed-basis grid.
    """
    # Fail fast on the FR-SAF-072 refusal before loading a model for a run that cannot proceed.
    config.require_torque_measurement()
    backend = select_backend(arm=config.arm, gravity_scale=config.gravity_scale)
    table = compute_residuals(grid, backend, config)
    j2_anomaly = detect_j2_anomaly(table)
    link7_impact = quantify_link7_transfer(_worst_wrist_pose(table), arm=config.arm)
    return VerificationReport(
        basis=table.basis,
        provisional=table.provisional,
        residual_table=table,
        j2_anomaly=j2_anomaly,
        link7_impact=link7_impact,
    )


def _worst_wrist_pose(table: ResidualTable) -> tuple[float, ...]:
    """Return the grid pose with the largest summed absolute wrist residual.

    The link7 impact is quantified there because that is the pose where a wrist residual, if it
    is an EE-mass problem, is most visible — tying the structural quantifier to the actual data.
    """
    worst = max(
        table.poses,
        key=lambda pose: sum(abs(pose.joints[joint].residual_nm) for joint in WRIST_JOINT_INDICES),
    )
    return worst.q


def _deferred_manifest(basis: MeasurementBasis) -> dict[str, Any]:
    """Record what the real measurement still needs and the hook that supplies it.

    Args:
        basis: The basis of the report being assembled.

    Returns:
        (dict[str, Any]) The awaited inputs and the re-verification hook, so the deferral is
        visible in the artifact rather than silent.
    """
    awaited = (
        []
        if basis is MeasurementBasis.REAL
        else [
            "real per-joint tau_meas grid captured on a torque-ON arm "
            "(use_velocity_and_torque=true)",
            "operator pose alignment and hold at each grid pose (SHAPE-HG)",
        ]
    )
    return {
        "awaited_inputs": awaited,
        "reverification_hook": REVERIFICATION_HOOK,
        "fixture_env_var": FIXTURE_ENV_VAR,
        "note": (
            "the real residual grid needs rig torque-ON plus operator pose alignment; a "
            "synthetic run is never asserted as a real PG-FRIC-001 preceding pass (THE ONE RULE)"
        ),
    }
