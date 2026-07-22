"""WP-2B-02: `MUJOCO_V2` exposes the Coriolis term the GMO needs; `URDF_KDL` is gravity-only.

Spec 12 §2.6 path B computes gravity+Coriolis from `qfrc_bias` on v2 inertia. The bias at zero
velocity is pure gravity, and the Coriolis term at zero velocity is zero; at non-zero velocity
it is non-zero and independent of the gravity trim.
"""

from __future__ import annotations

import pytest

from backend.gravity import Arm, MuJoCoV2GravityBackend

_ZERO_TOL_NM = 1.0e-9


def test_bias_at_zero_velocity_is_gravity(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """`tau_bias(q, 0)` equals `tau_grav(q)` because Coriolis vanishes at rest."""
    backend = MuJoCoV2GravityBackend()
    still = (0.0,) * 7
    for pose in pose_grid:
        bias = backend.tau_bias(pose, still)
        grav = backend.tau_grav(pose)
        for index in range(7):
            assert bias[index] == pytest.approx(grav[index], abs=_ZERO_TOL_NM)


def test_coriolis_is_zero_at_rest(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """`tau_coriolis(q, 0)` is zero for every pose."""
    backend = MuJoCoV2GravityBackend()
    still = (0.0,) * 7
    for pose in pose_grid:
        assert all(abs(term) < _ZERO_TOL_NM for term in backend.tau_coriolis(pose, still))


def test_coriolis_is_nonzero_in_motion() -> None:
    """Moving joints produce a non-zero Coriolis/centrifugal torque."""
    backend = MuJoCoV2GravityBackend()
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    moving = (0.8,) * 7
    assert max(abs(term) for term in backend.tau_coriolis(pose, moving)) > 1.0e-4


def test_gravity_trim_does_not_scale_coriolis() -> None:
    """`gravity_scale` trims gravity only; the Coriolis term is unchanged by it."""
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    moving = (0.8,) * 7
    full = MuJoCoV2GravityBackend(arm=Arm.RIGHT, gravity_scale=1.0)
    trimmed = MuJoCoV2GravityBackend(arm=Arm.RIGHT, gravity_scale=0.3)
    for index in range(7):
        assert trimmed.tau_coriolis(pose, moving)[index] == pytest.approx(
            full.tau_coriolis(pose, moving)[index], abs=1.0e-12
        )


def test_bias_trims_gravity_but_keeps_full_coriolis() -> None:
    """`tau_bias` at scale s is `Coriolis + s·gravity`, so it splits into the two terms."""
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    moving = (0.8,) * 7
    backend = MuJoCoV2GravityBackend(gravity_scale=0.5)
    coriolis = backend.tau_coriolis(pose, moving)
    gravity = backend.tau_grav(pose)  # already scaled by 0.5
    bias = backend.tau_bias(pose, moving)
    for index in range(7):
        assert bias[index] == pytest.approx(coriolis[index] + gravity[index], abs=1.0e-9)
