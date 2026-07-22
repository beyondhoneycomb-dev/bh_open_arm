"""Table the per-joint gravity difference between the two backends (WP-2B-02 acceptance ①).

Acceptance ① is that "the two backends compute `τ_grav` for the same pose and the difference
is tabled". This module produces that table. With `URDF_KDL` reading v2 inertia the difference
is at machine precision — a cross-validation of the default backend; a non-trivial difference
is the fingerprint the FR-SAF-034 negative branch keys on ("KDL does not reflect v2 inertia").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.gravity.backend import Arm
from backend.gravity.constants import GRAVITY_SCALE_DEFAULT
from backend.gravity.mujoco_v2 import MuJoCoV2GravityBackend
from backend.gravity.urdf_kdl import InertialParams, UrdfKdlGravityBackend


@dataclass(frozen=True)
class JointGravityDelta:
    """One joint's gravity torque under each backend and their absolute difference.

    Attributes:
        joint_index: Zero-based arm joint index (0 = joint1).
        mujoco_v2_nm: `MUJOCO_V2` gravity torque, Nm.
        urdf_kdl_nm: `URDF_KDL` gravity torque, Nm.
        abs_diff_nm: `|mujoco_v2_nm − urdf_kdl_nm|`, Nm.
    """

    joint_index: int
    mujoco_v2_nm: float
    urdf_kdl_nm: float
    abs_diff_nm: float


def compare_backends(
    q: Sequence[float],
    arm: Arm = Arm.RIGHT,
    gravity_scale: float = GRAVITY_SCALE_DEFAULT,
    inertial_params: InertialParams | None = None,
) -> tuple[JointGravityDelta, ...]:
    """Return the per-joint `τ_grav` difference between `MUJOCO_V2` and `URDF_KDL` at one pose.

    Args:
        q: One arm's seven joint angles, v2 convention, radians.
        arm: Which follower arm to compute for.
        gravity_scale: The gravity trim both backends use (kept equal so the table isolates the
            backend difference, not a scale difference).
        inertial_params: Optional inertia override for `URDF_KDL`; None reads v2 inertia.

    Returns:
        (tuple[JointGravityDelta, ...]) One row per joint, joint1..joint7 order.
    """
    mujoco_backend = MuJoCoV2GravityBackend(arm=arm, gravity_scale=gravity_scale)
    kdl_backend = UrdfKdlGravityBackend(
        arm=arm, gravity_scale=gravity_scale, inertial_params=inertial_params
    )
    mujoco_grav = mujoco_backend.tau_grav(q)
    kdl_grav = kdl_backend.tau_grav(q)
    return tuple(
        JointGravityDelta(
            joint_index=index,
            mujoco_v2_nm=mujoco_grav[index],
            urdf_kdl_nm=kdl_grav[index],
            abs_diff_nm=abs(mujoco_grav[index] - kdl_grav[index]),
        )
        for index in range(len(mujoco_grav))
    )


def format_delta_table(deltas: Sequence[JointGravityDelta]) -> str:
    """Render a comparison table as fixed-width text, one row per joint plus a max-diff footer.

    Args:
        deltas: The rows from `compare_backends`.

    Returns:
        (str) A text table with a header, one row per joint, and the worst-case difference.
    """
    header = f"{'joint':>6} {'MUJOCO_V2 [Nm]':>16} {'URDF_KDL [Nm]':>16} {'|diff| [Nm]':>14}"
    lines = [header, "-" * len(header)]
    for delta in deltas:
        lines.append(
            f"{delta.joint_index + 1:>6} {delta.mujoco_v2_nm:>16.6f} "
            f"{delta.urdf_kdl_nm:>16.6f} {delta.abs_diff_nm:>14.3e}"
        )
    worst = max((delta.abs_diff_nm for delta in deltas), default=0.0)
    lines.append(f"{'max |diff|':>6} {'':>16} {'':>16} {worst:>14.3e}")
    return "\n".join(lines)
