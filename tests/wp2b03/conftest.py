"""Shared fixtures for the WP-2B-03 gravity-model verification suite.

The pose grid is a small set of representative right-arm poses inside the v2 joint limits,
including the extended shoulder where gravity is largest. Poses are in the v2 joint convention —
the convention the WP-2B-02 backend verifies and computes in.

`unshifted_j2_deviation` builds the physically-grounded model error the joint-2 fingerprint must
catch: the difference between the shoulder gravity at the true v2 pose and at the pose whose
joint2 was left un-shifted by `-pi/2` (the WP-2B-01 shift not applied). It is derived from the
real backend, so the anomaly test is exercising a real sign error, not an arbitrary spike.
"""

from __future__ import annotations

import math

import pytest

from backend.gravity import Arm, GravityBackend, select_backend
from backend.gravity_verify import VerificationConfig
from backend.gravity_verify.constants import ARM_JOINT_COUNT, JOINT2_INDEX

_POSE_GRID = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1),
    (-0.5, 0.2, 0.9, 1.5, -0.7, 0.4, -1.0),
    (1.0, 1.5708, 0.0, 1.2, 1.0, 0.5, 0.6),
    (-1.0, 2.8, -1.2, 2.0, -1.3, -0.6, 1.2),
)


@pytest.fixture
def backend() -> GravityBackend:
    """The default WP-2B-02 MUJOCO_V2 gravity backend for the reference right arm."""
    return select_backend()


@pytest.fixture
def pose_grid() -> tuple[tuple[float, ...], ...]:
    """A small grid of in-limit right-arm poses, radians, v2 convention."""
    return _POSE_GRID


@pytest.fixture
def torque_on_config() -> VerificationConfig:
    """A config with torque measurement available (the run-permitting case)."""
    return VerificationConfig(use_velocity_and_torque=True, arm=Arm.RIGHT)


@pytest.fixture
def torque_off_config() -> VerificationConfig:
    """A config with torque measurement unavailable (the refusal case, FR-SAF-072)."""
    return VerificationConfig(use_velocity_and_torque=False, arm=Arm.RIGHT)


@pytest.fixture
def unshifted_j2_deviation(
    backend: GravityBackend, pose_grid: tuple[tuple[float, ...], ...]
) -> tuple[tuple[float, ...], ...]:
    """Per-pose model error a real arm would show if WP-2B-01's +pi/2 joint2 shift were missing.

    For each grid pose (the true v2 pose) it is `gravity(joint2 un-shifted) - gravity(true)`, so
    feeding it as the synthetic deviation makes the residual reproduce the shoulder sign error.
    """
    rows: list[tuple[float, ...]] = []
    for pose in pose_grid:
        unshifted = list(pose)
        unshifted[JOINT2_INDEX] = pose[JOINT2_INDEX] - math.pi / 2.0
        true_gravity = backend.tau_grav(pose)
        unshifted_gravity = backend.tau_grav(tuple(unshifted))
        rows.append(
            tuple(
                unshifted_gravity[joint] - true_gravity[joint] for joint in range(ARM_JOINT_COUNT)
            )
        )
    return tuple(rows)
