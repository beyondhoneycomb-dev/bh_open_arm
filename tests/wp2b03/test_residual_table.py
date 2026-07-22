"""WP-2B-03 acceptance ①: a per-joint `tau_meas - tau_model` residual for every grid pose.

The harness must record a residual for all seven joints at every pose in the grid, and the
residual must be exactly the measured-minus-modelled difference. A synthetic run is marked
provisional so it can never read as a real verdict.
"""

from __future__ import annotations

import pytest

from backend.gravity import GravityBackend
from backend.gravity_verify import (
    MeasurementBasis,
    VerificationConfig,
    compute_residuals,
    format_residual_table,
    synthesize_measurements,
)
from backend.gravity_verify.constants import ARM_JOINT_COUNT
from backend.gravity_verify.measurement import PoseMeasurement, grid_basis


def test_residual_recorded_for_every_pose_and_joint(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """Every pose yields a row and every row holds all seven joints (acceptance ①)."""
    grid = synthesize_measurements(pose_grid, backend)
    table = compute_residuals(grid, backend, torque_on_config)
    assert len(table.poses) == len(pose_grid)
    for pose in table.poses:
        assert len(pose.joints) == ARM_JOINT_COUNT
        assert tuple(j.joint_index for j in pose.joints) == tuple(range(ARM_JOINT_COUNT))
    assert len(table.joint_stats) == ARM_JOINT_COUNT


def test_residual_equals_measured_minus_modelled(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """The recorded residual is exactly `tau_meas - tau_model` at each joint."""
    grid = synthesize_measurements(pose_grid, backend)
    table = compute_residuals(grid, backend, torque_on_config)
    for pose in table.poses:
        for joint in pose.joints:
            assert joint.residual_nm == pytest.approx(joint.tau_meas_nm - joint.tau_model_nm)


def test_injected_deviation_appears_as_residual(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A known per-joint deviation is recovered as the residual (the arithmetic is honest)."""
    deviations = tuple((0.0, 0.5, -0.2, 0.0, 0.1, 0.0, -0.3) for _ in pose_grid)
    grid = synthesize_measurements(pose_grid, backend, deviations)
    table = compute_residuals(grid, backend, torque_on_config)
    for pose, deviation in zip(table.poses, deviations, strict=True):
        for joint, expected in zip(pose.joints, deviation, strict=True):
            assert joint.residual_nm == pytest.approx(expected, abs=1e-9)


def test_zero_deviation_gives_zero_residual(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A synthetic grid equal to the model has ~zero residual — the self-consistency baseline."""
    grid = synthesize_measurements(pose_grid, backend)
    table = compute_residuals(grid, backend, torque_on_config)
    for stat in table.joint_stats:
        assert stat.rms_nm == pytest.approx(0.0, abs=1e-9)


def test_synthetic_table_is_provisional(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A synthetic-basis table is provisional and stamps the synthetic basis."""
    grid = synthesize_measurements(pose_grid, backend)
    table = compute_residuals(grid, backend, torque_on_config)
    assert table.basis is MeasurementBasis.SYNTHETIC
    assert table.provisional is True


def test_real_basis_table_is_not_provisional(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A real-basis grid produces a non-provisional table."""
    grid = tuple(
        PoseMeasurement(q=pose, tau_meas=backend.tau_grav(pose), basis=MeasurementBasis.REAL)
        for pose in pose_grid
    )
    table = compute_residuals(grid, backend, torque_on_config)
    assert table.basis is MeasurementBasis.REAL
    assert table.provisional is False


def test_format_table_marks_provisional(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """The rendered table banner names the basis and marks a synthetic run provisional."""
    grid = synthesize_measurements(pose_grid, backend)
    text = format_residual_table(compute_residuals(grid, backend, torque_on_config))
    assert "synthetic-measurements" in text
    assert "PROVISIONAL" in text


def test_empty_grid_is_refused(
    backend: GravityBackend, torque_on_config: VerificationConfig
) -> None:
    """An empty grid is refused rather than yielding an empty table read as a pass."""
    with pytest.raises(ValueError, match="at least one measurement"):
        compute_residuals((), backend, torque_on_config)


def test_mixed_basis_grid_is_refused(backend: GravityBackend) -> None:
    """A grid mixing real and synthetic measurements is refused (no hiding synthetic in real)."""
    pose = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    tau = backend.tau_grav(pose)
    grid = (
        PoseMeasurement(q=pose, tau_meas=tau, basis=MeasurementBasis.REAL),
        PoseMeasurement(q=pose, tau_meas=tau, basis=MeasurementBasis.SYNTHETIC),
    )
    with pytest.raises(ValueError, match="all-real or all-synthetic"):
        grid_basis(grid)
