"""WP-2B-03: the link7-mass-moved-to-EE impact quantifier runs on the committed v2 model.

v2 folded the wrist-end (v1 link7) mass into the end-effector, so the quantifier measures that
relocated mass's share of each wrist joint's gravity. This exercises the wrist negative branch:
where the EE subtree dominates a wrist joint's gravity, a residual there is an EE mass/CoM error
to absorb into the payload model (WP-2B-04). No measured torque is needed — this reads the model.
"""

from __future__ import annotations

import mujoco

from backend.gravity import Arm
from backend.gravity.constants import MJCF_V2_PATH
from backend.gravity_verify.constants import WRIST_JOINT_INDICES
from backend.gravity_verify.link7 import ee_dominated_wrist_joints, quantify_link7_transfer

_EE_BODY_NAMES = (
    "openarm_right_ee_base_link",
    "openarm_right_ee_inner_finger",
    "openarm_right_ee_outer_finger",
)


def test_relocated_mass_is_the_ee_subtree_mass() -> None:
    """The reported relocated mass equals the summed end-effector subtree mass in the MJCF."""
    model = mujoco.MjModel.from_xml_path(str(MJCF_V2_PATH))
    expected = sum(
        float(model.body_mass[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)])
        for name in _EE_BODY_NAMES
    )
    impact = quantify_link7_transfer((0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1))
    assert impact.relocated_mass_kg == expected
    assert impact.relocated_mass_kg > 0.0


def test_wrist_joints_are_reported() -> None:
    """The impact covers exactly the three wrist joints, joint5..joint7."""
    impact = quantify_link7_transfer((0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1))
    assert tuple(w.joint_index for w in impact.wrist_joints) == WRIST_JOINT_INDICES


def test_relocated_mass_dominates_the_wrist() -> None:
    """The EE subtree accounts for essentially all wrist-joint gravity — the transfer's point."""
    impact = quantify_link7_transfer((0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1))
    for wrist in impact.wrist_joints:
        assert abs(wrist.ee_fraction) > 0.9
        assert wrist.ee_dominated is True
    assert ee_dominated_wrist_joints(impact) == WRIST_JOINT_INDICES


def test_ee_contribution_matches_mass_zeroing() -> None:
    """The reported EE contribution equals full-minus-zeroed gravity via the same qfrc_bias path.

    Recomputed here independently so the quantifier cannot silently diverge from mujoco's own
    bias force.
    """
    q = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    model = mujoco.MjModel.from_xml_path(str(MJCF_V2_PATH))
    data = mujoco.MjData(model)
    jids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"openarm_right_joint{i}")
        for i in range(1, 8)
    ]
    dofs = [int(model.jnt_dofadr[j]) for j in jids]
    for index, j in enumerate(jids):
        data.qpos[int(model.jnt_qposadr[j])] = q[index]
    mujoco.mj_forward(model, data)
    full = [float(data.qfrc_bias[d]) for d in dofs]

    reduced = mujoco.MjModel.from_xml_path(str(MJCF_V2_PATH))
    rdata = mujoco.MjData(reduced)
    for name in _EE_BODY_NAMES:
        reduced.body_mass[mujoco.mj_name2id(reduced, mujoco.mjtObj.mjOBJ_BODY, name)] = 0.0
    for index, j in enumerate(jids):
        rdata.qpos[int(reduced.jnt_qposadr[j])] = q[index]
    mujoco.mj_forward(reduced, rdata)
    reduced_bias = [float(rdata.qfrc_bias[d]) for d in dofs]

    impact = quantify_link7_transfer(q)
    for wrist in impact.wrist_joints:
        expected = full[wrist.joint_index] - reduced_bias[wrist.joint_index]
        assert abs(wrist.ee_contribution_nm - expected) < 1e-9


def test_left_arm_quantifies_independently() -> None:
    """The quantifier works for the left arm too (its own EE subtree)."""
    impact = quantify_link7_transfer((0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1), arm=Arm.LEFT)
    assert impact.relocated_mass_kg > 0.0
    assert len(impact.wrist_joints) == len(WRIST_JOINT_INDICES)
