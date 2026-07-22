"""WP-2B-02 negative-branch machinery: the difference table detects a KDL inertia mismatch.

FR-SAF-034's negative branch is "KDL re-implementation does not reflect v2 inertia →
RETRY_WITH_VARIANT (unify on MUJOCO_V2)". The fingerprint of that case is a non-trivial
difference in the acceptance-① table. This test feeds `URDF_KDL` a deliberately altered
inertia — synthetic, NOT a real v1 URDF — purely to prove the table would surface such a gap.
The altered result is never treated as a valid gravity model.
"""

from __future__ import annotations

from backend.gravity import (
    Arm,
    ArmModel,
    BackendId,
    InertialParams,
    compare_backends,
    select_backend,
)


def _perturbed_inertia(extra_wrist_mass_kg: float) -> InertialParams:
    """Return the v2 masses with a synthetic addition on the wrist body (not a real v1 URDF)."""
    arm_model = ArmModel(Arm.RIGHT)
    masses = [float(mass) for mass in arm_model.model.body_mass]
    wrist_body = int(arm_model.model.jnt_bodyid[arm_model.joint_ids[-1]])
    masses[wrist_body] += extra_wrist_mass_kg
    return InertialParams(tuple(masses))


def test_v2_inertia_gives_a_negligible_difference() -> None:
    """With the true v2 inertia, the table difference is at machine precision (no branch)."""
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    worst = max(delta.abs_diff_nm for delta in compare_backends(pose))
    assert worst < 1.0e-9


def test_altered_inertia_shows_up_as_a_tabled_difference() -> None:
    """A mismatched KDL inertia produces a non-trivial, tabled difference the branch keys on."""
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    deltas = compare_backends(pose, inertial_params=_perturbed_inertia(0.5))
    worst = max(delta.abs_diff_nm for delta in deltas)
    assert worst > 0.1


def test_altered_inertia_leaves_the_default_backend_untouched() -> None:
    """The MUJOCO_V2 column is unchanged by the KDL inertia override — only URDF_KDL moves."""
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    truth = select_backend(BackendId.MUJOCO_V2).tau_grav(pose)
    deltas = compare_backends(pose, inertial_params=_perturbed_inertia(0.5))
    for index, delta in enumerate(deltas):
        assert delta.mujoco_v2_nm == truth[index]
