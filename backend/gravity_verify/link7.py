"""Quantify the impact of the v2 link7-mass-moved-to-EE on the wrist-joint gravity term.

v2 has no link7 body: the wrist-end mass that in v1 was a separate link was folded into the
end-effector (spec 12 §2.6, FR-SAF-033, and the committed MJCF — link6 is followed directly by
`ee_base_link` and the two fingers). This module measures how much of each wrist joint's
modelled gravity comes from that relocated mass, by recomputing the gravity term with the
end-effector subtree's masses zeroed and taking the difference.

Why it matters (the WP-2B-03 wrist negative branch): where the EE-subtree mass accounts for
most of a wrist joint's gravity, any error in the EE mass or CoM lands almost entirely on that
joint's residual, so a large wrist residual is an EE-mass problem to absorb into the payload
model (WP-2B-04), not a gravity-convention problem. This runs on this host — the v2 MJCF loads
here — so it needs no measured torque and no deferral.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import mujoco

from backend.gravity.backend import Arm
from backend.gravity.model import ArmModel
from backend.gravity_verify.constants import WRIST_DOMINANCE_FRACTION, WRIST_JOINT_INDICES

# The relocated wrist-end mass is exactly the mass distal to joint7 — the end-effector subtree.
_JOINT7_INDEX = 6


@dataclass(frozen=True)
class WristJointImpact:
    """The relocated-mass gravity contribution on one wrist joint at a pose.

    Attributes:
        joint_index: Zero-based arm joint index (4=joint5, 5=joint6, 6=joint7).
        total_gravity_nm: The joint's full modelled gravity torque, Nm.
        ee_contribution_nm: The part of it due to the end-effector (relocated link7) subtree, Nm.
        ee_fraction: `ee_contribution_nm / total_gravity_nm`, or 0 when the total is ~0.
        ee_dominated: True when the EE subtree accounts for at least `WRIST_DOMINANCE_FRACTION`
            of this joint's gravity, i.e. its residual is governed by EE mass/CoM accuracy.
    """

    joint_index: int
    total_gravity_nm: float
    ee_contribution_nm: float
    ee_fraction: float
    ee_dominated: bool


@dataclass(frozen=True)
class Link7TransferImpact:
    """The link7->EE transfer impact at one pose.

    Attributes:
        q: The pose it was quantified at, seven joint angles, v2 convention, radians.
        relocated_mass_kg: Total mass of the end-effector subtree — the mass v2 relocated.
        wrist_joints: The per-wrist-joint impact, joint5..joint7 order.
    """

    q: tuple[float, ...]
    relocated_mass_kg: float
    wrist_joints: tuple[WristJointImpact, ...]


def quantify_link7_transfer(q: Sequence[float], arm: Arm = Arm.RIGHT) -> Link7TransferImpact:
    """Measure the relocated end-effector mass's share of each wrist joint's gravity at `q`.

    The full gravity is read from the v2 model; a second copy of the model has the end-effector
    subtree masses zeroed, and the per-joint difference is the relocated mass's contribution.
    The two share the identical `qfrc_bias` path the WP-2B-02 backend uses, so the contribution
    is consistent with the modelled torque the residual harness subtracts.

    Args:
        q: The static pose to quantify at, seven joint angles, v2 convention, radians.
        arm: Which follower arm to quantify for.

    Returns:
        (Link7TransferImpact) The relocated mass and its per-wrist-joint gravity contribution.
    """
    full_model = ArmModel(arm)
    ee_bodies = full_model.subtrees[_JOINT7_INDEX]

    full_gravity = _gravity(full_model, q)

    reduced_model = ArmModel(arm)
    relocated_mass = 0.0
    for body in ee_bodies:
        relocated_mass += float(reduced_model.model.body_mass[body])
        reduced_model.model.body_mass[body] = 0.0
    reduced_gravity = _gravity(reduced_model, q)

    wrist_joints = tuple(
        _wrist_impact(joint, full_gravity[joint], full_gravity[joint] - reduced_gravity[joint])
        for joint in WRIST_JOINT_INDICES
    )
    return Link7TransferImpact(
        q=tuple(float(angle) for angle in q),
        relocated_mass_kg=relocated_mass,
        wrist_joints=wrist_joints,
    )


def ee_dominated_wrist_joints(impact: Link7TransferImpact) -> tuple[int, ...]:
    """Return the wrist joints whose gravity is dominated by the relocated EE mass.

    These are the joints the WP-2B-03 negative branch routes to the payload model: a large
    residual on an EE-dominated wrist joint is an EE mass/CoM error, absorbed as EE mass in
    WP-2B-04, not a gravity-convention error.

    Args:
        impact: The quantified transfer impact.

    Returns:
        (tuple[int, ...]) The zero-based indices of the EE-dominated wrist joints.
    """
    return tuple(joint.joint_index for joint in impact.wrist_joints if joint.ee_dominated)


def _gravity(model: ArmModel, q: Sequence[float]) -> tuple[float, ...]:
    """Return the arm's per-joint gravity torque from a model's `qfrc_bias` at zero velocity."""
    model.set_pose(q)
    mujoco.mj_forward(model.model, model.data)
    return model.arm_dofs(model.data.qfrc_bias)


def _wrist_impact(joint: int, total_nm: float, ee_nm: float) -> WristJointImpact:
    """Build one wrist joint's impact record from its total and EE-attributed gravity."""
    fraction = ee_nm / total_nm if abs(total_nm) > 0.0 else 0.0
    return WristJointImpact(
        joint_index=joint,
        total_gravity_nm=total_nm,
        ee_contribution_nm=ee_nm,
        ee_fraction=fraction,
        ee_dominated=abs(fraction) >= WRIST_DOMINANCE_FRACTION,
    )
