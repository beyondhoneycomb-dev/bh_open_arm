"""The IK adapter: ordered build, controlled fallback, fault-reported solve.

This is the WP-0C-02 deliverable that ties the pieces together. ``build_ik_adapter``
is the sanctioned entry point — it runs the FR-SIM-080 order (ArmSetup → jnt_range
override → verify → Kinematics) through ``OrderedIkBuild``, so a caller cannot get an
adapter whose limits were snapshotted before the override.

The solve loop is re-implemented here rather than delegated to
``_IKSolver.solve`` for one reason: that method hard-codes the unconstrained
``limits=[]`` retry (kinematics.py:220-231), and FR-SAF-016 requires the fallback to
be *disabled by default* and *reported as a fault when enabled*. An absence that the
library forces on cannot be delegated to the library; the loop below drives
``openarm_control``'s own mink objects (the ``_IKSolver`` this adapter built) and
differs from the upstream loop in exactly one place — the fallback is an opt-in,
per-firing-counted branch instead of a silent one.

Every solve runs the four FR-OPS-043 detectors — ``solve() → None``, EE residual,
unconstrained fallback, joint-limit clamp — and any firing transitions the adapter
to HOLD, emitting the distinct ``OA-IK-*`` code and holding the last valid joint
angles. IK output is radians (CTR-UNIT ``Rad``); the accepted action crosses to
LeRobot degrees through the one sanctioned ``rad_to_deg`` boundary and is clamped to
the LeRobot soft limits, yielding a CTR-ACT ``AcceptedPositionAction``.
"""

from __future__ import annotations

from dataclasses import dataclass

import mink
import mink.exceptions
import numpy as np
from openarm_control.config import ArmSetup
from openarm_control.kinematics import IKParams, Kinematics

from contracts.action.channels import AcceptedPositionAction
from contracts.units.conversions import rad_to_deg
from contracts.units.tags import Deg, Rad
from sim.ik.asset import (
    EE_FRAME_TYPE,
    HOME_KEYFRAME,
    LEFT_EE_SITE,
    RIGHT_EE_SITE,
    fixed_cell_xml,
)
from sim.ik.faults import FaultReporter, IkFault, IkFaultCode
from sim.ik.limits import JointLimit, all_soft_limits
from sim.ik.override import OrderedIkBuild

# Solution layout: two arms of eight driver values (seven joints + one gripper).
SIDE_WIDTH = 8
ARM_JOINTS_PER_SIDE = 7
BIMANUAL_WIDTH = 16

# Clamp comparison tolerance in radians; a value within this of a bound is inside.
CLAMP_TOLERANCE = 1e-9


@dataclass(frozen=True)
class IkOutcome:
    """The result of one solve cycle.

    Attributes:
        accepted: The post-clamp position action in degrees, or None only when no
            prior valid pose exists to hold.
        held: True when a fault forced a HOLD, so ``accepted`` is the last valid
            pose rather than this cycle's solution.
        faults: The FR-OPS-043 faults detected this cycle, distinctly coded.
        solution_rad: The raw IK solution in radians, or None on ``solve() → None``.
    """

    accepted: AcceptedPositionAction | None
    held: bool
    faults: tuple[IkFault, ...]
    solution_rad: np.ndarray | None


class IkAdapter:
    """Ordered, fallback-controlled, fault-reporting wrapper over ``Kinematics``.

    Built only through ``build_ik_adapter`` so the FR-SIM-080 order is guaranteed.
    Not thread-safe: one adapter serves one solve thread, holding the mink
    configuration and the last-valid pose across cycles. The unconstrained fallback
    is disabled unless ``allow_unconstrained_fallback`` was set at build; when
    enabled, every firing is one ``OA-IK-003`` fault (FR-SAF-016 — never silent).
    """

    def __init__(
        self,
        kinematics: Kinematics,
        setup: ArmSetup,
        limits: tuple[JointLimit, ...],
        allow_unconstrained_fallback: bool,
        residual_max_m: float | None,
    ) -> None:
        """Initialize; prefer ``build_ik_adapter`` which enforces the build order.

        Args:
            kinematics: The solver built over the overridden model.
            setup: The ArmSetup backing ``kinematics``.
            limits: The LeRobot soft limits used for override and output clamp.
            allow_unconstrained_fallback: Whether the ``limits=[]`` retry may run.
            residual_max_m: EE residual threshold in metres, or None to leave the
                residual gate uncalibrated (WP-0C-04 / PG-IK-001 fixes the value).
        """
        self._kin = kinematics
        self._ik = kinematics._require_ik()
        self._setup = setup
        self._limits = limits
        self._allow_fallback = allow_unconstrained_fallback
        self._residual_max_m = residual_max_m
        self._reporter = FaultReporter()
        self._targets: dict[str, np.ndarray] = {}
        self._last_valid = self._home_solution()

    # -- configuration -----------------------------------------------------------

    @property
    def allow_unconstrained_fallback(self) -> bool:
        """Return whether the unconstrained fallback is enabled (default False)."""
        return self._allow_fallback

    @property
    def residual_max_m(self) -> float | None:
        """Return the EE residual threshold, or None when the gate is uncalibrated."""
        return self._residual_max_m

    def set_residual_max_m(self, residual_max_m: float | None) -> None:
        """Set the EE residual threshold (metres); None disables the residual gate."""
        self._residual_max_m = residual_max_m

    # -- targets and state -------------------------------------------------------

    def set_target(self, side: str, pose: np.ndarray) -> None:
        """Set one arm's EE target and remember it for residual checking.

        Args:
            side: ``"right"`` or ``"left"``.
            pose: float[7] = [px, py, pz, qw, qx, qy, qz].
        """
        self._kin.set_target(side, pose)
        self._targets[side] = np.asarray(pose, dtype=float).copy()

    def sync(self, values16: np.ndarray) -> None:
        """Seed the IK configuration from a 16-value driver state (right[8]+left[8])."""
        self._kin.sync(values16)

    def set_gripper(self, side: str, value: float) -> None:
        """Pass a gripper value through; IK does not solve for it."""
        self._kin.set_gripper(side, value)

    # -- solve -------------------------------------------------------------------

    def solve(self) -> IkOutcome:
        """Run one controlled IK cycle and report the four FR-OPS-043 conditions.

        Returns:
            (IkOutcome) The accepted action or a HOLD, with any distinct faults.
        """
        self._reporter.reset()
        solution = self._run_solve_loop()

        if solution is None:
            self._reporter.report(
                IkFault(
                    code=IkFaultCode.SOLVE_NONE,
                    detail="constrained QP found no solution; unconstrained fallback "
                    + ("failed" if self._allow_fallback else "disabled by default"),
                )
            )
            return self._hold()

        self._check_residual(solution)
        clamped = self._check_and_clamp(solution)

        if self._reporter.any_fault:
            return self._hold(solution_rad=solution)

        self._last_valid = clamped
        return IkOutcome(
            accepted=_to_accepted_action(clamped),
            held=False,
            faults=(),
            solution_rad=solution,
        )

    def _run_solve_loop(self) -> np.ndarray | None:
        """Drive the mink solve loop with the fallback under this adapter's control.

        Mirrors ``_IKSolver.solve`` (kinematics.py:198-245) except the ``limits=[]``
        retry runs only when the fallback is enabled, and each firing is one
        ``OA-IK-003`` fault.

        Returns:
            (np.ndarray | None) The float32[16] solution, or None when no solution
            exists under the active limit policy.
        """
        ik = self._ik
        tasks = list(ik._tasks.values())
        if ik._posture_cost > 0.0:
            tasks.append(ik._posture_task)
        constraints = [ik._freeze_task] if ik._freeze_task else []

        for _ in range(ik._max_iters):
            try:
                vel = mink.solve_ik(
                    ik._config,
                    tasks,
                    ik._dt,
                    ik._solver_name,
                    limits=ik._limits,
                    constraints=constraints,
                    safety_break=False,
                    **ik._solver_params,
                )
            except mink.exceptions.NoSolutionFound:
                if not self._allow_fallback:
                    return None
                self._reporter.report(
                    IkFault(
                        code=IkFaultCode.UNCONSTRAINED_FALLBACK,
                        detail="constrained QP failed; retried with limits=[], "
                        "discarding the soft limits (12 FR-SAF-016)",
                    )
                )
                try:
                    vel = mink.solve_ik(
                        ik._config,
                        tasks,
                        ik._dt,
                        ik._solver_name,
                        limits=[],
                        constraints=constraints,
                        safety_break=False,
                        **ik._solver_params,
                    )
                except mink.exceptions.NoSolutionFound:
                    return None
            ik._config.integrate_inplace(vel, ik._dt)

        ik._pending = set(ik._sides)
        qpos = ik._config.data.qpos
        right_joints, _ = ik._joint_resolver.get_driver(qpos, "right")
        left_joints, _ = ik._joint_resolver.get_driver(qpos, "left")
        return np.concatenate(
            [
                np.append(right_joints, ik._gripper[0]),
                np.append(left_joints, ik._gripper[1]),
            ]
        ).astype(np.float32)

    def _check_residual(self, solution: np.ndarray) -> None:
        """Emit ``OA-IK-002`` when an arm's EE residual exceeds the threshold.

        Skipped when the residual gate is uncalibrated (threshold None) — the value
        is fixed by WP-0C-04 / PG-IK-001, not nailed here.

        Args:
            solution: The float[16] IK solution to forward-kinematics.
        """
        if self._residual_max_m is None or not self._targets:
            return
        right = np.asarray(solution[:SIDE_WIDTH], dtype=float)
        left = np.asarray(solution[SIDE_WIDTH:], dtype=float)
        pose_right, pose_left = self._kin.fk_bimanual(right, left)
        achieved = {"right": pose_right, "left": pose_left}
        for side, target in self._targets.items():
            residual = float(np.linalg.norm(target[:3] - achieved[side][:3]))
            if residual > self._residual_max_m:
                self._reporter.report(
                    IkFault(
                        code=IkFaultCode.EE_RESIDUAL_EXCEEDED,
                        detail=f"{side} EE residual {residual:.4f} m exceeds "
                        f"{self._residual_max_m:.4f} m",
                        joint=side,
                        magnitude=residual,
                    )
                )

    def _check_and_clamp(self, solution: np.ndarray) -> np.ndarray:
        """Clamp the solution to the LeRobot soft limits, emitting ``OA-IK-004``.

        On the constrained path ``ConfigurationLimit`` keeps the solution inside the
        limits, so a clamp here means an out-of-limit solution reached this point —
        which only the unconstrained fallback produces.

        Args:
            solution: The float[16] IK solution in radians.

        Returns:
            (np.ndarray) The clamped solution, aligned to the 16-slot layout.
        """
        clamped = np.asarray(solution, dtype=float).copy()
        for slot, limit in enumerate(self._limits):
            lower = limit.lower_rad.value
            upper = limit.upper_rad.value
            value = clamped[slot]
            if value < lower - CLAMP_TOLERANCE:
                self._reporter.report(_clamp_fault(limit.mjcf_joint, lower - value))
                clamped[slot] = lower
            elif value > upper + CLAMP_TOLERANCE:
                self._reporter.report(_clamp_fault(limit.mjcf_joint, value - upper))
                clamped[slot] = upper
        return clamped

    def _hold(self, solution_rad: np.ndarray | None = None) -> IkOutcome:
        """Build a HOLD outcome that keeps the last valid joint angles.

        Args:
            solution_rad: The raw solution that triggered the hold, if any.

        Returns:
            (IkOutcome) A held outcome carrying the recorded faults.
        """
        accepted = _to_accepted_action(self._last_valid) if self._last_valid is not None else None
        return IkOutcome(
            accepted=accepted,
            held=True,
            faults=self._reporter.faults,
            solution_rad=solution_rad,
        )

    def _home_solution(self) -> np.ndarray:
        """Read the model's current driver state as the initial last-valid pose."""
        qpos = self._setup.data.qpos
        right_joints, right_grip = self._setup.joint_resolver.get_driver(qpos, "right")
        left_joints, left_grip = self._setup.joint_resolver.get_driver(qpos, "left")
        return np.concatenate(
            [
                np.append(right_joints, float(right_grip)),
                np.append(left_joints, float(left_grip)),
            ]
        ).astype(np.float32)


def _clamp_fault(joint: str, overshoot: float) -> IkFault:
    """Build one joint-limit clamp fault (``OA-IK-004``)."""
    return IkFault(
        code=IkFaultCode.JOINT_LIMIT_CLAMP,
        detail=f"{joint} clamped to the LeRobot soft limit (overshoot {overshoot:.4f} rad)",
        joint=joint,
        magnitude=overshoot,
    )


def _to_accepted_action(solution_rad: np.ndarray) -> AcceptedPositionAction:
    """Convert a radian solution to a CTR-ACT degrees action through ``rad_to_deg``.

    The finger joint is a hinge in this asset, so every slot — arm joints and
    gripper alike — is a radian angle, and the single CTR-UNIT ``rad_to_deg``
    crossing carries the whole vector to the LeRobot degree convention the action
    channel is defined in.

    Args:
        solution_rad: The float[16] clamped solution in radians.

    Returns:
        (AcceptedPositionAction) The 16-dim degrees action.
    """
    values = tuple(rad_to_deg(Rad(float(value))) for value in solution_rad)
    return AcceptedPositionAction(values=_as_deg_tuple(values))


def _as_deg_tuple(values: tuple[Deg, ...]) -> tuple[Deg, ...]:
    """Reject a width other than the bimanual action dimension, then return as-is."""
    if len(values) != BIMANUAL_WIDTH:
        raise ValueError(f"IK solution must be {BIMANUAL_WIDTH}-dim, got {len(values)}")
    return values


def build_ik_adapter(
    xml: str | None = None,
    mode: str = "bimanual",
    ik_params: IKParams | None = None,
    allow_unconstrained_fallback: bool = False,
    residual_max_m: float | None = None,
    keyframe: str | None = HOME_KEYFRAME,
) -> IkAdapter:
    """Build an IK adapter through the FR-SIM-080 order (the sanctioned entry point).

    The order — ArmSetup → jnt_range override → verify → Kinematics — is enforced by
    ``OrderedIkBuild``; there is no way through this factory to reach a Kinematics
    whose limits predate the override.

    Args:
        xml: MJCF path; None uses the WP-0C-03 fixed cell asset.
        mode: ``"right"``, ``"left"``, or ``"bimanual"``.
        ik_params: mink IK parameters; None uses ``openarm_control`` defaults.
        allow_unconstrained_fallback: Whether the ``limits=[]`` retry may run
            (default False — FR-SAF-016).
        residual_max_m: EE residual threshold in metres, or None to leave the
            residual gate uncalibrated.
        keyframe: Initial keyframe name; the cell's ``home`` by default.

    Returns:
        (IkAdapter) A ready adapter over the overridden model.

    Raises:
        LimitMismatchError: When the post-override jnt_range does not match LeRobot.
    """
    asset = xml if xml is not None else str(fixed_cell_xml())
    setup = ArmSetup.from_args(
        xml=asset,
        mode=mode,
        frame_right=RIGHT_EE_SITE,
        frame_type_right=EE_FRAME_TYPE,
        frame_left=LEFT_EE_SITE,
        frame_type_left=EE_FRAME_TYPE,
        keyframe=keyframe,
    )

    limits = all_soft_limits()
    build = OrderedIkBuild(setup)
    build.override_joint_ranges(limits)
    kinematics = build.build_kinematics(ik_params if ik_params is not None else IKParams())

    return IkAdapter(
        kinematics=kinematics,
        setup=setup,
        limits=limits,
        allow_unconstrained_fallback=allow_unconstrained_fallback,
        residual_max_m=residual_max_m,
    )
