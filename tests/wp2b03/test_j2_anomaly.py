"""WP-2B-03 acceptance ②: the joint-2 residual-anomaly check is real, two-sided logic.

The +pi/2-shift fingerprint must fire on an un-shifted model and stay quiet on a correct one.
Both directions are tested so the check is proven to be a discriminator, not a rubber stamp:
a correct model leaves joint2 comparable to its peers (not flagged), an un-shifted model makes
joint2 dominate (flagged), and sub-Nm noise never trips it.
"""

from __future__ import annotations

from backend.gravity import GravityBackend
from backend.gravity_verify import (
    VerificationConfig,
    compute_residuals,
    detect_j2_anomaly,
    synthesize_measurements,
)
from backend.gravity_verify.constants import JOINT2_INDEX


def test_matching_model_is_not_anomalous(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """When measurement equals model, joint2 is not flagged (the healthy case)."""
    grid = synthesize_measurements(pose_grid, backend)
    result = detect_j2_anomaly(compute_residuals(grid, backend, torque_on_config))
    assert result.is_anomalous is False


def test_small_uniform_noise_is_not_anomalous(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """Sub-floor scatter on joint2 does not trip the check, even at a high ratio."""
    # Joint2 at 0.3 Nm, others near zero: ratio is large but joint2 is below the 0.5 Nm floor.
    deviations = tuple((0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0) for _ in pose_grid)
    grid = synthesize_measurements(pose_grid, backend, deviations)
    result = detect_j2_anomaly(compute_residuals(grid, backend, torque_on_config))
    assert result.joint2_rms_nm < result.abs_floor_nm
    assert result.is_anomalous is False


def test_unshifted_model_is_flagged(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
    unshifted_j2_deviation: tuple[tuple[float, ...], ...],
) -> None:
    """The physically-derived un-shifted shoulder error is flagged as the fingerprint (②)."""
    grid = synthesize_measurements(pose_grid, backend, unshifted_j2_deviation)
    result = detect_j2_anomaly(compute_residuals(grid, backend, torque_on_config))
    assert result.is_anomalous is True
    assert result.ratio >= result.ratio_threshold
    assert result.joint2_rms_nm >= result.abs_floor_nm


def test_joint2_dominates_peers_when_unshifted(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
    unshifted_j2_deviation: tuple[tuple[float, ...], ...],
) -> None:
    """The fingerprint is joint2 dominance: its residual is the largest in the table."""
    grid = synthesize_measurements(pose_grid, backend, unshifted_j2_deviation)
    table = compute_residuals(grid, backend, torque_on_config)
    joint2 = table.joint_stats[JOINT2_INDEX].rms_nm
    peers = [s.rms_nm for s in table.joint_stats if s.joint_index != JOINT2_INDEX]
    assert joint2 == max(joint2, *peers)


def test_large_uniform_bias_is_not_a_j2_fingerprint(
    backend: GravityBackend,
    pose_grid: tuple[tuple[float, ...], ...],
    torque_on_config: VerificationConfig,
) -> None:
    """A large residual spread evenly across joints is not the joint2 fingerprint.

    A whole-arm scale error (every joint biased alike) must not masquerade as the shoulder sign
    error, or the check would fire on the wrong fault and send WP-2B-01 to be re-run needlessly.
    """
    deviations = tuple((2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0) for _ in pose_grid)
    grid = synthesize_measurements(pose_grid, backend, deviations)
    result = detect_j2_anomaly(compute_residuals(grid, backend, torque_on_config))
    assert result.is_anomalous is False
