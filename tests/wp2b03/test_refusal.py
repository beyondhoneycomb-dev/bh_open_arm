"""WP-2B-03 acceptance ③: `use_velocity_and_torque=false` refuses the verification run.

The refusal is the contract, not a warning: with the switch off there is no `.torque` channel
and therefore no `tau_meas`, so a residual cannot be formed and the run is refused (FR-SAF-072,
spec 09 FR-SIM-025b). The refusal must fire at every entry point that would otherwise touch a
measurement.
"""

from __future__ import annotations

import pytest

from backend.gravity import GravityBackend
from backend.gravity_verify import (
    VerificationConfig,
    VerificationRefusedError,
    compute_residuals,
    run_verification,
    synthesize_measurements,
)


def test_config_gate_refuses_when_torque_unavailable(
    torque_off_config: VerificationConfig,
) -> None:
    """The config's own gate refuses directly."""
    with pytest.raises(VerificationRefusedError, match="use_velocity_and_torque"):
        torque_off_config.require_torque_measurement()


def test_config_gate_permits_when_torque_available(
    torque_on_config: VerificationConfig,
) -> None:
    """With the switch on the gate is a no-op (does not raise)."""
    torque_on_config.require_torque_measurement()


def test_compute_residuals_refuses_without_torque(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_off_config: VerificationConfig,
) -> None:
    """The residual harness refuses before forming any residual."""
    grid = synthesize_measurements(pose_grid, backend)
    with pytest.raises(VerificationRefusedError):
        compute_residuals(grid, backend, torque_off_config)


def test_run_verification_refuses_without_torque(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_off_config: VerificationConfig,
) -> None:
    """The orchestrator refuses too — the refusal is not bypassable through the top-level run."""
    grid = synthesize_measurements(pose_grid, backend)
    with pytest.raises(VerificationRefusedError):
        run_verification(grid, torque_off_config)


def test_refusal_is_a_value_error() -> None:
    """The refusal is catchable as the package error and as a plain ValueError."""
    config = VerificationConfig(use_velocity_and_torque=False)
    with pytest.raises(ValueError):
        config.require_torque_measurement()
