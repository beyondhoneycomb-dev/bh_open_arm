"""Elbow-swivel nullspace over the reused Cartesian jog (WP-2D-02, FR-MAN-024).

FR-MAN-024 admits two implementations of nullspace elbow control — manipulating mink's
posture-task *target* vector, or adding a separate nullspace task — and warns that
``posture_cost`` is a neutral-posture *weight*, not an elbow API. The reused IK's
posture target is fixed to the model midpoint and is not exposed, and a weight cannot
command a swivel *angle*, so this takes the separate-nullspace-task route:

- The 6x7 Jacobian's one-dimensional nullspace gives the elbow self-motion direction
  (``ArmJacobian.nullspace_direction``).
- The EE is re-fixed to its frozen pose through the *reused* WP-2D-01 IK
  (``jog.seed`` + ``jog.plan_pose``) — never a second solver.

Because the reused IK's EE task pulls the EE back to the frozen pose, the swivel keeps
the EE fixed by construction (acceptance ①); the nullspace implementation does not move
the EE, so the RETRY_WITH_VARIANT branch does not fire. The requested angle is applied
in sub-steps, each re-fixed to the *same* frozen pose so drift never accumulates, and a
sub-step the reused IK cannot satisfy (a limit, no solution, a singularity) restores the
pre-swivel configuration exactly, returning the EE to where it started rather than
leaving it at the drifted seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from backend.cartesian_jog import JogStopReason, ReferenceFrame, TcpSelection
from backend.cartesian_jog.frames import pose_position, pose_quat, quat_geodesic_angle
from backend.singularity.constants import (
    ARM_JOINTS_PER_SIDE,
    SIDE_WIDTH,
    SIDES,
    SWIVEL_SUBSTEP_MAX_RAD,
)
from backend.singularity.kinematics import ArmJacobian

if TYPE_CHECKING:
    from backend.cartesian_jog import CartesianJog


@dataclass(frozen=True)
class SwivelResult:
    """The outcome of one elbow-swivel application.

    Attributes:
        applied: True when the full requested swivel committed with the EE held fixed.
        reason: The jog stop category when a sub-step was rejected, else None.
        ee_translation_drift_m: EE position drift from the frozen pose, by FK (acceptance ①).
        ee_rotation_drift_rad: EE orientation drift from the frozen pose, by FK.
        arm_delta_rad: The Euclidean norm of the arm-joint change the swivel produced.
        substeps: How many sub-steps the requested angle was split into.
        detail: Human-readable context for the operator log.
    """

    applied: bool
    reason: JogStopReason | None
    ee_translation_drift_m: float
    ee_rotation_drift_rad: float
    arm_delta_rad: float
    substeps: int
    detail: str


class ElbowSwivel:
    """Swivels an arm's elbow through the Jacobian nullspace while the reused IK holds the EE.

    Not thread-safe: it drives one jog on one thread. It mutates only the jog's committed
    configuration, through the jog's own ``seed``/``plan_pose`` surface; on a rejected
    sub-step it restores the configuration captured at entry. Because ``seed`` clears any
    latched jog stop, a swivel is a deliberate operation that resumes the jog; a rejected
    swivel leaves the committed pose exactly as it was found, not the pre-existing stop.
    """

    def __init__(self, jog: CartesianJog, jacobian: ArmJacobian) -> None:
        """Initialize; prefer ``build_elbow_swivel`` which builds the Jacobian context.

        Args:
            jog: The WP-2D-01 Cartesian jog to swivel (its IK re-fixes the EE).
            jacobian: The FK/Jacobian context, over the same asset as ``jog``.
        """
        self._jog = jog
        self._jacobian = jacobian

    def swivel(self, side: str, delta_rad: float, tcp: TcpSelection | None = None) -> SwivelResult:
        """Swivel ``side``'s elbow by ``delta_rad`` while holding the EE pose fixed.

        Args:
            side: ``"right"`` or ``"left"``.
            delta_rad: The signed swivel angle to apply; sign selects the swivel direction.
            tcp: The TCP whose pose is held fixed; None uses the jog's default TCP.

        Returns:
            (SwivelResult) The outcome, with the FK-measured EE drift (acceptance ①).
        """
        side = _require_side(side)
        tcp = tcp if tcp is not None else self._jog.default_tcp
        base = 0 if side == "right" else SIDE_WIDTH
        joint_slice = slice(base, base + ARM_JOINTS_PER_SIDE)

        config_before = self._jog.committed_solution()
        frozen_ee = self._jog.current_pose(side, ReferenceFrame.WORLD, tcp)

        substeps = int(np.ceil(abs(delta_rad) / SWIVEL_SUBSTEP_MAX_RAD)) if delta_rad else 0
        if substeps == 0:
            return SwivelResult(
                applied=True,
                reason=None,
                ee_translation_drift_m=0.0,
                ee_rotation_drift_rad=0.0,
                arm_delta_rad=0.0,
                substeps=0,
                detail="zero swivel: no change",
            )

        sub_delta = delta_rad / substeps
        for index in range(substeps):
            current = self._jog.committed_solution()
            direction = self._jacobian.nullspace_direction(side, current[joint_slice])
            seed = current.copy()
            seed[joint_slice] = current[joint_slice] + sub_delta * direction
            self._jog.seed(seed)
            result = self._jog.plan_pose(side, frozen_ee, ReferenceFrame.WORLD, tcp, commit=True)
            if not result.committed:
                self._jog.seed(config_before)
                return SwivelResult(
                    applied=False,
                    reason=result.reason,
                    ee_translation_drift_m=0.0,
                    ee_rotation_drift_rad=0.0,
                    arm_delta_rad=0.0,
                    substeps=index,
                    detail=f"swivel rejected at sub-step {index}: {result.detail}",
                )

        achieved_ee = self._jog.current_pose(side, ReferenceFrame.WORLD, tcp)
        drift_m = float(np.linalg.norm(pose_position(achieved_ee) - pose_position(frozen_ee)))
        drift_rad = quat_geodesic_angle(pose_quat(achieved_ee), pose_quat(frozen_ee))
        arm_delta = float(
            np.linalg.norm(self._jog.committed_solution()[joint_slice] - config_before[joint_slice])
        )
        return SwivelResult(
            applied=True,
            reason=None,
            ee_translation_drift_m=drift_m,
            ee_rotation_drift_rad=drift_rad,
            arm_delta_rad=arm_delta,
            substeps=substeps,
            detail=f"swiveled {side} elbow by {delta_rad:.4f} rad, EE held fixed",
        )


def _require_side(side: str) -> str:
    """Return ``side`` if it is a valid arm, else reject."""
    if side not in SIDES:
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    return side
