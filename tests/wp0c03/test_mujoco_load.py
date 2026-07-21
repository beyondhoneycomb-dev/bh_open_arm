"""Acceptance ②③⑧ — the fixed MJCF compiles and its J7/J2 params are the v2 truth.

These assertions go through the MuJoCo compiler: ``from_xml_path`` must succeed, J7
must resolve to the DM4310 dynamics on both arms, the J7 actuator must be the same
DM4310 family, and J2 must carry the v2 limits. The sim stack is the optional
``[robot]`` group, so the module skips where MuJoCo is absent.
"""

from __future__ import annotations

import pytest

from tests.wp0c03 import BIMANUAL_XML, CELL_REPARENTED_XML, CELL_XML

mujoco = pytest.importorskip("mujoco")

DM4310_FRICTIONLOSS = 0.04
DM4310_DAMPING = 0.9
DM4310_ARMATURE = 0.0100
DM4310_FORCERANGE = 7.0
TOLERANCE = 1e-6

BIMANUAL_NQ_NV_NU = (18, 18, 16)
CELL_NQ_NV_NU = (19, 19, 17)


def _model(path: str):
    return mujoco.MjModel.from_xml_path(str(path))


def _joint_dynamics(model, name: str) -> tuple[float, float, float]:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    dof = model.jnt_dofadr[joint_id]
    return (
        float(model.dof_frictionloss[dof]),
        float(model.dof_damping[dof]),
        float(model.dof_armature[dof]),
    )


def _joint_range(model, name: str) -> tuple[float, float]:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    low, high = model.jnt_range[joint_id]
    return float(low), float(high)


def _actuator_forcerange(model, name: str) -> tuple[float, float]:
    actuator_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
    low, high = model.actuator_forcerange[actuator_id]
    return float(low), float(high)


def test_fixed_bimanual_compiles() -> None:
    model = _model(BIMANUAL_XML)
    assert (model.nq, model.nv, model.nu) == BIMANUAL_NQ_NV_NU


def test_cell_scenes_compile() -> None:
    for path in (CELL_XML, CELL_REPARENTED_XML):
        model = _model(path)
        assert (model.nq, model.nv, model.nu) == CELL_NQ_NV_NU


@pytest.mark.parametrize("joint", ["openarm_left_joint7", "openarm_right_joint7"])
def test_j7_resolves_to_dm4310(joint: str) -> None:
    model = _model(BIMANUAL_XML)
    frictionloss, damping, armature = _joint_dynamics(model, joint)
    assert abs(frictionloss - DM4310_FRICTIONLOSS) < TOLERANCE
    assert abs(damping - DM4310_DAMPING) < TOLERANCE
    assert abs(armature - DM4310_ARMATURE) < TOLERANCE


def test_j7_matches_j5_and_j6_dynamics() -> None:
    model = _model(BIMANUAL_XML)
    j5 = _joint_dynamics(model, "openarm_left_joint5")
    j6 = _joint_dynamics(model, "openarm_left_joint6")
    j7 = _joint_dynamics(model, "openarm_left_joint7")
    assert j7 == j5 == j6


@pytest.mark.parametrize("actuator", ["left_joint7_ctrl", "right_joint7_ctrl"])
def test_j7_actuator_is_dm4310_forcerange(actuator: str) -> None:
    model = _model(BIMANUAL_XML)
    low, high = _actuator_forcerange(model, actuator)
    assert abs(low + DM4310_FORCERANGE) < TOLERANCE
    assert abs(high - DM4310_FORCERANGE) < TOLERANCE


def test_j2_limits_are_v2() -> None:
    model = _model(BIMANUAL_XML)
    assert _joint_range(model, "openarm_right_joint2") == pytest.approx((-0.17453, 3.3161))
    assert _joint_range(model, "openarm_left_joint2") == pytest.approx((-3.3161, 0.17453))


def test_no_v1_shoulder_range_remains() -> None:
    model = _model(BIMANUAL_XML)
    v1_bound = 1.745329
    for joint_id in range(model.njnt):
        low, high = model.jnt_range[joint_id]
        is_v1 = abs(abs(low) - v1_bound) < TOLERANCE and abs(abs(high) - v1_bound) < TOLERANCE
        assert not is_v1
