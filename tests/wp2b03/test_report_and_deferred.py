"""WP-2B-03 report assembly: contract note, provisional flag, and the deferred manifest.

The report must carry the WP-2B-03 contract on its face — preceding evidence for PG-FRIC-001,
not a gate — mark a synthetic run provisional, and ship a deferred manifest naming the real
torque-ON pose grid it still needs and the re-verification hook that consumes it.
"""

from __future__ import annotations

from backend.gravity import GravityBackend
from backend.gravity_verify import (
    MeasurementBasis,
    VerificationConfig,
    run_verification,
    synthesize_measurements,
)
from backend.gravity_verify.harness import (
    FIXTURE_ENV_VAR,
    PG_PRECEDING,
    REVERIFICATION_HOOK,
    WP_ID,
)
from backend.gravity_verify.measurement import PoseMeasurement


def test_synthetic_report_is_provisional(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A synthetic run yields a provisional report with awaited real inputs."""
    grid = synthesize_measurements(pose_grid, backend)
    report = run_verification(grid, torque_on_config)
    assert report.basis is MeasurementBasis.SYNTHETIC
    assert report.provisional is True
    record = report.as_record()
    assert record["provisional"] is True
    assert len(record["deferred"]["awaited_inputs"]) == 2


def test_report_carries_the_preceding_evidence_contract(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """The record names WP-2B-03 as PG-FRIC-001 preceding evidence, not a gate."""
    grid = synthesize_measurements(pose_grid, backend)
    record = run_verification(grid, torque_on_config).as_record()
    assert record["wp_id"] == WP_ID
    assert record["preceding_evidence_for"] == PG_PRECEDING
    assert "not a separate gate" in record["contract_note"]


def test_deferred_manifest_names_hook_and_fixture(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """The deferral is explicit: the hook path and its fixture env var are recorded."""
    grid = synthesize_measurements(pose_grid, backend)
    deferred = run_verification(grid, torque_on_config).as_record()["deferred"]
    assert deferred["reverification_hook"] == REVERIFICATION_HOOK
    assert deferred["fixture_env_var"] == FIXTURE_ENV_VAR
    assert "torque-ON" in " ".join(deferred["awaited_inputs"])
    assert "operator pose alignment" in " ".join(deferred["awaited_inputs"])


def test_report_surfaces_the_j2_and_link7_results(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
    unshifted_j2_deviation: tuple[tuple[float, ...], ...],
) -> None:
    """The record exposes the anomaly verdict and the link7 impact for downstream reads."""
    grid = synthesize_measurements(pose_grid, backend, unshifted_j2_deviation)
    record = run_verification(grid, torque_on_config).as_record()
    assert record["j2_anomaly"]["is_anomalous"] is True
    assert record["link7_transfer"]["relocated_mass_kg"] > 0.0
    assert record["link7_transfer"]["ee_dominated_wrist_joints"] == [4, 5, 6]
    assert len(record["joint_residual_rms_nm"]) == 7


def test_real_basis_report_awaits_nothing(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A real-basis grid produces a non-provisional report with an empty awaited-input list."""
    grid = tuple(
        PoseMeasurement(q=pose, tau_meas=backend.tau_grav(pose), basis=MeasurementBasis.REAL)
        for pose in pose_grid
    )
    record = run_verification(grid, torque_on_config).as_record()
    assert record["provisional"] is False
    assert record["deferred"]["awaited_inputs"] == []
