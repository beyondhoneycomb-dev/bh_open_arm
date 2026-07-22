"""The pose-grid residual harness: per-joint `tau_meas - tau_model` over the whole grid (①).

For every pose in the grid this computes the modelled gravity from the WP-2B-02 backend and
subtracts it from the measured torque, per joint, and rolls the grid up into per-joint
aggregate statistics the anomaly check reads. The table carries its measurement basis and a
`provisional` flag: a table built from any synthetic measurement is provisional and is never a
real PG-FRIC-001 preceding result.

The harness refuses to run at all when torque measurement is unavailable (FR-SAF-072), so the
acceptance-③ refusal is enforced here, at the single point a residual would otherwise be formed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from backend.gravity.backend import GravityBackend
from backend.gravity_verify.config import VerificationConfig
from backend.gravity_verify.constants import ARM_JOINT_COUNT
from backend.gravity_verify.measurement import MeasurementBasis, PoseMeasurement, grid_basis


@dataclass(frozen=True)
class JointResidual:
    """One joint's measured torque, modelled torque, and their signed residual at one pose.

    Attributes:
        joint_index: Zero-based arm joint index (0 = joint1).
        tau_meas_nm: The measured joint torque, Nm.
        tau_model_nm: The modelled gravity torque from the WP-2B-02 backend, Nm.
        residual_nm: `tau_meas_nm - tau_model_nm`, Nm.
    """

    joint_index: int
    tau_meas_nm: float
    tau_model_nm: float
    residual_nm: float


@dataclass(frozen=True)
class PoseResidual:
    """The per-joint residuals at one pose.

    Attributes:
        q: The pose, seven joint angles, v2 convention, radians.
        joints: One `JointResidual` per joint, joint1..joint7 order.
    """

    q: tuple[float, ...]
    joints: tuple[JointResidual, ...]


@dataclass(frozen=True)
class JointResidualStats:
    """One joint's residual aggregated across every pose in the grid.

    Attributes:
        joint_index: Zero-based arm joint index (0 = joint1).
        mean_nm: Mean signed residual across poses, Nm.
        max_abs_nm: Largest absolute residual across poses, Nm.
        rms_nm: Root-mean-square residual across poses, Nm — the magnitude the anomaly check
            keys on, because it is insensitive to sign but sensitive to a single large pose.
    """

    joint_index: int
    mean_nm: float
    max_abs_nm: float
    rms_nm: float


@dataclass(frozen=True)
class ResidualTable:
    """The whole-grid residual result (①): per-pose rows and per-joint aggregate statistics.

    Attributes:
        basis: The measurement basis the grid was on.
        provisional: True when the basis is synthetic; a provisional table is never a real
            PG-FRIC-001 preceding result.
        poses: One `PoseResidual` per pose, in grid order.
        joint_stats: One `JointResidualStats` per joint, joint1..joint7 order.
    """

    basis: MeasurementBasis
    provisional: bool
    poses: tuple[PoseResidual, ...]
    joint_stats: tuple[JointResidualStats, ...]


def compute_residuals(
    grid: Sequence[PoseMeasurement],
    backend: GravityBackend,
    config: VerificationConfig,
) -> ResidualTable:
    """Build the per-joint residual table over the whole pose grid (acceptance ①).

    Refuses the run when torque measurement is unavailable (FR-SAF-072, acceptance ③) before
    forming any residual.

    Args:
        grid: The pose/measurement grid; all-real or all-synthetic (a mix is refused).
        backend: The WP-2B-02 gravity backend that supplies `tau_model`.
        config: The run configuration; its torque-availability gate is checked first.

    Returns:
        (ResidualTable) The per-pose residuals and per-joint aggregate statistics.

    Raises:
        VerificationRefusedError: If `config.use_velocity_and_torque` is False.
        GravityVerifyError: On an empty or mixed-basis grid.
    """
    config.require_torque_measurement()
    basis = grid_basis(grid)

    pose_residuals = tuple(_pose_residual(measurement, backend) for measurement in grid)
    joint_stats = tuple(_joint_stats(pose_residuals, joint) for joint in range(ARM_JOINT_COUNT))
    return ResidualTable(
        basis=basis,
        provisional=basis is MeasurementBasis.SYNTHETIC,
        poses=pose_residuals,
        joint_stats=joint_stats,
    )


def _pose_residual(measurement: PoseMeasurement, backend: GravityBackend) -> PoseResidual:
    """Compute the per-joint residual at one measured pose."""
    model = backend.tau_grav(measurement.q)
    joints = tuple(
        JointResidual(
            joint_index=joint,
            tau_meas_nm=measurement.tau_meas[joint],
            tau_model_nm=model[joint],
            residual_nm=measurement.tau_meas[joint] - model[joint],
        )
        for joint in range(ARM_JOINT_COUNT)
    )
    return PoseResidual(q=measurement.q, joints=joints)


def _joint_stats(pose_residuals: Sequence[PoseResidual], joint: int) -> JointResidualStats:
    """Aggregate one joint's residual across every pose."""
    residuals = [pose.joints[joint].residual_nm for pose in pose_residuals]
    count = len(residuals)
    mean = sum(residuals) / count
    max_abs = max(abs(value) for value in residuals)
    rms = math.sqrt(sum(value * value for value in residuals) / count)
    return JointResidualStats(joint_index=joint, mean_nm=mean, max_abs_nm=max_abs, rms_nm=rms)


def format_residual_table(table: ResidualTable) -> str:
    """Render the per-joint aggregate statistics as fixed-width text with a provisional banner.

    Args:
        table: The residual table from `compute_residuals`.

    Returns:
        (str) A text table with a basis banner, one row per joint, and RMS/max/mean columns.
    """
    suffix = " (PROVISIONAL — not a real verdict)" if table.provisional else ""
    banner = f"basis={table.basis.value}{suffix}"
    header = f"{'joint':>6} {'rms [Nm]':>12} {'max|res| [Nm]':>14} {'mean [Nm]':>12}"
    lines = [banner, header, "-" * len(header)]
    for stat in table.joint_stats:
        lines.append(
            f"{stat.joint_index + 1:>6} {stat.rms_nm:>12.4f} "
            f"{stat.max_abs_nm:>14.4f} {stat.mean_nm:>12.4f}"
        )
    return "\n".join(lines)
