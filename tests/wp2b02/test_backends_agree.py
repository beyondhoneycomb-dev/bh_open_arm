"""WP-2B-02 acceptance ①: the two backends compute `tau_grav` for the same pose, difference tabled.

`URDF_KDL` reading v2 inertia is an independent computation (KDL potential-energy projection
over forward kinematics) from `MUJOCO_V2` (the RNE `qfrc_bias`), so their agreement to machine
precision cross-validates the default backend. The difference table is the acceptance artifact.
"""

from __future__ import annotations

from backend.gravity import (
    Arm,
    BackendId,
    compare_backends,
    format_delta_table,
    select_backend,
)

# The two backends use only mass and centre-of-mass for gravity, computed two different ways,
# so agreement is to floating-point rounding, not a physical tolerance.
_AGREEMENT_TOL_NM = 1.0e-9


def test_difference_table_has_a_row_per_joint(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """`compare_backends` tables both backends and their difference for all seven joints."""
    for pose in pose_grid:
        deltas = compare_backends(pose)
        assert len(deltas) == 7
        for index, delta in enumerate(deltas):
            assert delta.joint_index == index
            assert delta.abs_diff_nm == abs(delta.mujoco_v2_nm - delta.urdf_kdl_nm)


def test_backends_agree_to_machine_precision(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """Both backends fed v2 inertia return the same gravity torque across the pose grid."""
    for pose in pose_grid:
        deltas = compare_backends(pose)
        worst = max(delta.abs_diff_nm for delta in deltas)
        assert worst < _AGREEMENT_TOL_NM, f"{worst} at pose {pose}\n{format_delta_table(deltas)}"


def test_agreement_holds_on_both_arms(pose_grid: tuple[tuple[float, ...], ...]) -> None:
    """The cross-check holds for the left arm too, not only the right reference arm."""
    for arm in (Arm.RIGHT, Arm.LEFT):
        mujoco_backend = select_backend(BackendId.MUJOCO_V2, arm=arm)
        kdl_backend = select_backend(BackendId.URDF_KDL, arm=arm)
        for pose in pose_grid:
            mujoco_grav = mujoco_backend.tau_grav(pose)
            kdl_grav = kdl_backend.tau_grav(pose)
            worst = max(abs(a - b) for a, b in zip(mujoco_grav, kdl_grav, strict=True))
            assert worst < _AGREEMENT_TOL_NM


def test_format_delta_table_is_readable(zero_pose: tuple[float, ...]) -> None:
    """The rendered table carries both backend columns and a max-difference footer."""
    table = format_delta_table(compare_backends(zero_pose))
    assert "MUJOCO_V2" in table
    assert "URDF_KDL" in table
    assert "max |diff|" in table
    assert len(table.splitlines()) == 7 + 3  # header, rule, seven joints, footer
