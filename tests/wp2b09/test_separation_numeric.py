"""Acceptance ① — the control side runs friction*0.3 + Coriolis*0.1 while the residual runs 100%.

Demonstrated numerically on the committed v2 `MUJOCO_V2` backend (WP-2B-02): the two torque
computations read the same gravity and Coriolis from the one backend and the same friction vector,
and differ only by the scale set. The detection torque is invariant to the control scale — the
proof that the residual model cannot be moved by retuning the feedforward.
"""

from __future__ import annotations

import pytest

from backend.compscale import (
    ControlCompensationScales,
    ScaleSeparationError,
    control_feedforward_torque,
    detection_model_torque,
)
from backend.gravity import MuJoCoV2GravityBackend

_ABS_TOL_NM = 1.0e-9


def test_detection_is_full_model_reconstruction(
    pose_grid: tuple[tuple[float, ...], ...],
    moving_velocity: tuple[float, ...],
    synthetic_friction: tuple[float, ...],
) -> None:
    """The detection torque equals `g + C·q̇ + tau_fric` at full scale, term by term."""
    backend = MuJoCoV2GravityBackend()
    for pose in pose_grid:
        gravity = backend.tau_grav(pose)
        coriolis = backend.tau_coriolis(pose, moving_velocity)
        model = detection_model_torque(backend, pose, moving_velocity, synthetic_friction)
        for index in range(7):
            expected = gravity[index] + coriolis[index] + synthetic_friction[index]
            assert model[index] == pytest.approx(expected, abs=_ABS_TOL_NM)


def test_control_applies_partial_friction_and_coriolis(
    pose_grid: tuple[tuple[float, ...], ...],
    moving_velocity: tuple[float, ...],
    synthetic_friction: tuple[float, ...],
) -> None:
    """The control feedforward equals `g + 0.1·C·q̇ + 0.3·tau_fric`, term by term."""
    backend = MuJoCoV2GravityBackend()
    scales = ControlCompensationScales()
    for pose in pose_grid:
        gravity = backend.tau_grav(pose)
        coriolis = backend.tau_coriolis(pose, moving_velocity)
        feedforward = control_feedforward_torque(
            backend, pose, moving_velocity, synthetic_friction, scales
        )
        for index in range(7):
            expected = gravity[index] + 0.1 * coriolis[index] + 0.3 * synthetic_friction[index]
            assert feedforward[index] == pytest.approx(expected, abs=_ABS_TOL_NM)


def test_residual_uses_full_model_not_the_control_scale(
    pose_grid: tuple[tuple[float, ...], ...],
    moving_velocity: tuple[float, ...],
    synthetic_friction: tuple[float, ...],
) -> None:
    """The detection/control difference is the un-compensated fraction: `0.9·C·q̇ + 0.7·tau_fric`.

    This is the term that would land in the residual as a standing error if the residual were
    computed with the control scale instead of the full model (FR-SAF-035).
    """
    backend = MuJoCoV2GravityBackend()
    scales = ControlCompensationScales()
    for pose in pose_grid:
        coriolis = backend.tau_coriolis(pose, moving_velocity)
        model = detection_model_torque(backend, pose, moving_velocity, synthetic_friction)
        feedforward = control_feedforward_torque(
            backend, pose, moving_velocity, synthetic_friction, scales
        )
        for index in range(7):
            uncompensated = 0.9 * coriolis[index] + 0.7 * synthetic_friction[index]
            assert model[index] - feedforward[index] == pytest.approx(
                uncompensated, abs=_ABS_TOL_NM
            )


def test_detection_torque_is_invariant_to_control_scale(
    moving_velocity: tuple[float, ...],
    synthetic_friction: tuple[float, ...],
) -> None:
    """Retuning the control scale does not move the detection model torque."""
    backend = MuJoCoV2GravityBackend()
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    baseline = detection_model_torque(backend, pose, moving_velocity, synthetic_friction)
    for friction_scale, coriolis_scale in ((0.3, 0.1), (0.0, 0.0), (1.0, 1.0), (0.5, 0.2)):
        control_feedforward_torque(
            backend,
            pose,
            moving_velocity,
            synthetic_friction,
            ControlCompensationScales(friction_scale=friction_scale, coriolis_scale=coriolis_scale),
        )
        again = detection_model_torque(backend, pose, moving_velocity, synthetic_friction)
        assert again == baseline


def test_friction_vector_width_is_checked(
    moving_velocity: tuple[float, ...],
) -> None:
    """A friction vector of the wrong width is refused rather than silently truncated."""
    backend = MuJoCoV2GravityBackend()
    pose = (0.0,) * 7
    with pytest.raises(ScaleSeparationError):
        detection_model_torque(backend, pose, moving_velocity, (0.0,) * 6)
