"""The 6x7 arm Jacobian, its singular values, and the signed nullspace direction.

The monitor and the swivel both stand on this one Jacobian. What it must guarantee: the
right shape (a 6-DoF twist over seven joints), singular values that fall as the elbow
straightens toward a real singularity, and a nullspace direction that annihilates the
Jacobian and carries a deterministic sign so the swivel slider has a stable direction.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.singularity import ArmJacobian
from backend.singularity.constants import ARM_JOINTS_PER_SIDE, SPATIAL_DIM

_HOME = np.array([0.0, 0.0, 0.0, np.pi / 2, 0.0, 0.0, 0.0])


def _straightening(elbow: float) -> np.ndarray:
    """Return a right-arm config with joint4 (the elbow) at ``elbow`` radians."""
    joints = _HOME.copy()
    joints[3] = elbow
    return joints


def test_jacobian_is_six_by_seven() -> None:
    jac = ArmJacobian()
    for side in ("right", "left"):
        assert jac.jacobian(side, _HOME).shape == (SPATIAL_DIM, ARM_JOINTS_PER_SIDE)


def test_jacobian_rejects_wrong_joint_count() -> None:
    jac = ArmJacobian()
    with pytest.raises(ValueError):
        jac.jacobian("right", np.zeros(6))


def test_singular_values_fall_as_the_elbow_straightens() -> None:
    jac = ArmJacobian()
    # joint4 = pi/2 is well-conditioned; driving it toward 0 straightens the elbow into
    # a singularity, so the smallest singular value must decrease monotonically.
    sigma_mins = [
        float(jac.singular_values("right", _straightening(elbow))[-1])
        for elbow in (1.5, 1.0, 0.5, 0.1)
    ]
    assert sigma_mins == sorted(sigma_mins, reverse=True)
    assert sigma_mins[-1] < 0.05


def test_nullspace_direction_annihilates_the_jacobian() -> None:
    jac = ArmJacobian()
    for side in ("right", "left"):
        joints = _straightening(0.7)
        direction = jac.nullspace_direction(side, joints)
        assert direction.shape == (ARM_JOINTS_PER_SIDE,)
        assert float(np.linalg.norm(direction)) == pytest.approx(1.0, abs=1e-9)
        residual = float(np.linalg.norm(jac.jacobian(side, joints) @ direction))
        assert residual < 1e-6


def test_nullspace_sign_is_deterministic() -> None:
    jac = ArmJacobian()
    joints = _straightening(0.8)
    direction = jac.nullspace_direction("right", joints)
    # Dominant-magnitude component positive, and stable across repeated evaluation.
    dominant = int(np.argmax(np.abs(direction)))
    assert direction[dominant] > 0.0
    again = jac.nullspace_direction("right", joints)
    assert np.allclose(direction, again)
