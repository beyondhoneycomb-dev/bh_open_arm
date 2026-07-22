"""Cartesian jog adapter over the reused sim.ik solver (WP-2D-01).

A jog is a small Cartesian delta — six translation buttons and six rotation buttons —
turned into an EE target and driven through the Wave 0-C IK adapter (``sim.ik``). This
adapter never builds a second IK: ``build_cartesian_jog`` reaches ``Kinematics`` only
through ``sim.ik.build_ik_adapter``, which enforces the FR-SIM-080 order (ArmSetup →
jnt_range override → Kinematics), and the static scan proves this file references no
banned solver symbol. What this layer adds is the jog geometry (reference frames, TCP,
the q_lift reflection) and the operator-facing contract that a failed step *holds and
reports* rather than silently skipping.

The IK is the first line of defense (02b §4.3): its clamp and hold decide whether a
step is admissible, and a held outcome becomes a jog stop with a categorized reason
(``NoSolutionFound`` / limit / singularity / residual / fallback). A failed step never
advances the committed pose and never rolls on to the next command — it latches the
jog stopped until ``resume`` (acceptance ④: zero step-skips, immediate hold). As a
redundant guard, the committed solution is re-checked against the canonical mechanical
limits before it is accepted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from openarm_control.kinematics import IKParams

from backend.cartesian_jog.constants import (
    ARM_JOINTS_PER_SIDE,
    BIMANUAL_WIDTH,
    CLAMP_FIRST_DEFENSE_NOTE,
    DEFAULT_ROTATION_STEP_RAD,
    DEFAULT_TRANSLATION_STEP_M,
    FULL_VELOCITY_SCALE,
    MAX_ROTATION_STEP_RAD,
    MAX_TRANSLATION_STEP_M,
    MIN_VELOCITY_SCALE,
    MOVE_TO_MAX_CYCLES,
    MOVE_TO_TOLERANCE_M,
    MOVE_TO_TOLERANCE_RAD,
    SIDE_WIDTH,
    SIDES,
    TCP_DEFAULT_NOTE,
)
from backend.cartesian_jog.frames import (
    KinematicFrames,
    ReferenceFrame,
    axis_angle_to_quat,
    compose_pose,
    invert_pose,
    make_pose,
    pose_position,
    pose_quat,
    quat_geodesic_angle,
    quat_mul,
    rotate_vec,
)
from backend.cartesian_jog.tcp import TcpSelection, ToolCenterPoint
from contracts.action.channels import AcceptedPositionAction
from sim.ik.adapter import IkAdapter, IkOutcome, build_ik_adapter
from sim.ik.faults import IkFault, IkFaultCode
from sim.ik.limits import all_soft_limits

# The three Cartesian axes; the unit column of each in the frame it is named in.
_AXIS_UNIT = {
    "x": np.array([1.0, 0.0, 0.0]),
    "y": np.array([0.0, 1.0, 0.0]),
    "z": np.array([0.0, 0.0, 1.0]),
}

_MECHANICAL_LIMIT_TOLERANCE_RAD = 1e-6


class JogAxis(Enum):
    """The Cartesian axis a jog button acts on."""

    X = "x"
    Y = "y"
    Z = "z"


class JogKind(Enum):
    """Whether a jog button translates or rotates the TCP."""

    TRANSLATION = "translation"
    ROTATION = "rotation"


class JogStopReason(Enum):
    """Why a jog step held instead of advancing (acceptance ④'s categories).

    ``SINGULARITY`` is raised by the WP-2D-02 monitor through
    ``set_singularity_monitor``; the other four map one-to-one from the ``sim.ik``
    ``OA-IK-*`` fault codes.
    """

    NO_SOLUTION = "no_solution_found"
    LIMIT = "mechanical_limit"
    SINGULARITY = "singularity"
    RESIDUAL = "ee_residual"
    FALLBACK = "unconstrained_fallback"


# Fault-to-reason mapping and the priority used when a held step carries several.
_REASON_BY_CODE = {
    IkFaultCode.SOLVE_NONE: JogStopReason.NO_SOLUTION,
    IkFaultCode.JOINT_LIMIT_CLAMP: JogStopReason.LIMIT,
    IkFaultCode.UNCONSTRAINED_FALLBACK: JogStopReason.FALLBACK,
    IkFaultCode.EE_RESIDUAL_EXCEEDED: JogStopReason.RESIDUAL,
}
_REASON_PRIORITY = (
    JogStopReason.SINGULARITY,
    JogStopReason.NO_SOLUTION,
    JogStopReason.LIMIT,
    JogStopReason.FALLBACK,
    JogStopReason.RESIDUAL,
)


@dataclass(frozen=True)
class JogCommand:
    """One jog button press.

    Attributes:
        side: ``"right"`` or ``"left"`` — the arm to jog.
        kind: Translation or rotation.
        axis: The Cartesian axis.
        sign: ``+1`` or ``-1`` — the button's direction.
        frame: The reference frame the delta is expressed in.
        tcp: The tool-center point the jog acts on.
    """

    side: str
    kind: JogKind
    axis: JogAxis
    sign: int
    frame: ReferenceFrame = ReferenceFrame.WORLD
    tcp: TcpSelection = TcpSelection.FLANGE


@dataclass(frozen=True)
class JogResult:
    """The outcome of one jog step or move.

    Attributes:
        committed: True when the step advanced the committed pose.
        stopped: True when the jog is held; ``committed`` is then False.
        reason: The stop category when ``stopped``, else None.
        accepted: The IK-accepted degrees action, or None on a hold with no prior pose.
        solution_rad: The raw float[16] radian solution, or None when the solve held.
        target_world: The commanded TCP target in the physical world frame.
        achieved_world: The TCP world pose after a committed step, else None.
        faults: The ``sim.ik`` faults behind a hold, in report order.
        fallback_fired: True when the unconstrained fallback fired this step.
        detail: Human-readable context for the operator log.
    """

    committed: bool
    stopped: bool
    reason: JogStopReason | None
    accepted: AcceptedPositionAction | None
    solution_rad: np.ndarray | None
    target_world: np.ndarray | None
    achieved_world: np.ndarray | None
    faults: tuple[IkFault, ...] = ()
    fallback_fired: bool = False
    detail: str = ""


# A monitor WP-2D-02 installs: given the jogged side and its arm joints, it returns a
# reason string to hold on (a near-singular Jacobian) or None to allow the step.
SingularityMonitor = Callable[[str, np.ndarray], "str | None"]


class CartesianJog:
    """Frame-aware Cartesian jog driving the reused sim.ik adapter.

    Not thread-safe: one jog serves one operator thread, holding the committed 16-value
    arm state, the lifter height, and the latched stop state across steps. All IK goes
    through the injected ``IkAdapter`` (built by ``build_cartesian_jog`` through the
    ordered builder); this class owns geometry and the stop/hold contract, not a solver.
    """

    def __init__(
        self,
        adapter: IkAdapter,
        frames: KinematicFrames,
        tcp: ToolCenterPoint,
        ik_params: IKParams,
        reference_frame: ReferenceFrame,
        default_tcp: TcpSelection,
        q_lift: float,
        xml: str | None,
        mode: str,
    ) -> None:
        """Initialize; prefer ``build_cartesian_jog`` which enforces the IK build order."""
        self._adapter = adapter
        self._frames = frames
        self._tcp = tcp
        self._ik_params = ik_params
        self._reference_frame = reference_frame
        self._default_tcp = default_tcp
        self._xml = xml
        self._mode = mode
        self._translation_step_m = DEFAULT_TRANSLATION_STEP_M
        self._rotation_step_rad = DEFAULT_ROTATION_STEP_RAD
        self._velocity_scale = FULL_VELOCITY_SCALE
        self._singularity_monitor: SingularityMonitor | None = None
        self._committed = self._frames.home_solution()
        self._adapter.sync(self._committed)
        self._q_lift = 0.0
        self.set_q_lift(q_lift)
        self._stopped = False
        self._stop_reason: JogStopReason | None = None
        self._steps_committed = 0
        self._steps_held = 0

    # -- configuration -----------------------------------------------------------

    @property
    def reference_frame(self) -> ReferenceFrame:
        """Return the default reference frame for a command that omits one."""
        return self._reference_frame

    def set_reference_frame(self, frame: ReferenceFrame) -> None:
        """Set the default reference frame."""
        self._reference_frame = frame

    @property
    def default_tcp(self) -> TcpSelection:
        """Return the default TCP for a command that omits one."""
        return self._default_tcp

    def select_tcp(self, tcp: TcpSelection) -> None:
        """Set the default TCP selection."""
        self._default_tcp = tcp

    def tcp_default_note(self) -> str:
        """Return the UI note that the default TCP is the flange, not the grasp point."""
        return TCP_DEFAULT_NOTE

    def clamp_note(self) -> str:
        """Return the UI note that a legal IK solution may still be held or clamped."""
        return CLAMP_FIRST_DEFENSE_NOTE

    @property
    def translation_step_m(self) -> float:
        """Return the translation increment in metres."""
        return self._translation_step_m

    def set_translation_step_m(self, step_m: float) -> None:
        """Set the translation increment, capped at ``MAX_TRANSLATION_STEP_M``."""
        if not 0.0 < step_m <= MAX_TRANSLATION_STEP_M:
            raise ValueError(f"translation step must be in (0, {MAX_TRANSLATION_STEP_M}] m")
        self._translation_step_m = step_m

    @property
    def rotation_step_rad(self) -> float:
        """Return the rotation increment in radians."""
        return self._rotation_step_rad

    def set_rotation_step_rad(self, step_rad: float) -> None:
        """Set the rotation increment, capped at ``MAX_ROTATION_STEP_RAD``."""
        if not 0.0 < step_rad <= MAX_ROTATION_STEP_RAD:
            raise ValueError(f"rotation step must be in (0, {MAX_ROTATION_STEP_RAD}] rad")
        self._rotation_step_rad = step_rad

    @property
    def velocity_scale(self) -> float:
        """Return the current velocity scale (1.0 unless a monitor damped it)."""
        return self._velocity_scale

    def set_velocity_scale(self, scale: float) -> None:
        """Scale jog increments in (MIN_VELOCITY_SCALE, 1]; WP-2D-02 damps near singularities."""
        if not MIN_VELOCITY_SCALE <= scale <= FULL_VELOCITY_SCALE:
            raise ValueError(f"velocity scale must be in [{MIN_VELOCITY_SCALE}, 1.0]")
        self._velocity_scale = scale

    def set_singularity_monitor(self, monitor: SingularityMonitor | None) -> None:
        """Install the WP-2D-02 monitor consulted before each step; None clears it."""
        self._singularity_monitor = monitor

    @property
    def ik_params(self) -> IKParams:
        """Return the IK parameters currently in force."""
        return self._ik_params

    def set_ik_params(self, ik_params: IKParams) -> None:
        """Rebuild the IK adapter with new parameters, preserving arm state and settings.

        Runtime exposure of the mink parameters (dt, max_iters, costs) means a rebuild:
        the ordered builder is the only sanctioned way to a Kinematics, so the adapter
        is rebuilt through it rather than mutated in place, then re-seeded to the
        committed pose so the jog continues from where it stood.
        """
        rebuilt = build_ik_adapter(
            xml=self._xml,
            mode=self._mode,
            ik_params=ik_params,
            allow_unconstrained_fallback=self._adapter.allow_unconstrained_fallback,
            residual_max_m=self._adapter.residual_max_m,
        )
        rebuilt.sync(self._committed)
        self._adapter = rebuilt
        self._ik_params = ik_params

    @property
    def allow_unconstrained_fallback(self) -> bool:
        """Return whether the unconstrained fallback is enabled (default False)."""
        return self._adapter.allow_unconstrained_fallback

    def set_residual_max_m(self, residual_max_m: float | None) -> None:
        """Set the EE residual threshold on the underlying IK adapter."""
        self._adapter.set_residual_max_m(residual_max_m)

    # -- lifter / q_lift ---------------------------------------------------------

    @property
    def q_lift(self) -> float:
        """Return the reflected lifter height in metres."""
        return self._q_lift

    def set_q_lift(self, q_lift: float) -> None:
        """Set the lifter height, clamped to the model's travel; reflected into the base frame."""
        low, high = self._frames.lifter_range
        self._q_lift = float(np.clip(q_lift, low, high))

    def reflect_world_to_ik(self, side: str, pose_world: np.ndarray) -> np.ndarray:
        """Reflect a physical-world pose onto the IK world (base at lift zero).

        ``sim.ik`` freezes the lifter and solves with it at zero, so its world places
        the base at the home height. A world target the operator commands must lose the
        lifter displacement to land in that world; skipping this is the up-to-0.3 m
        systematic error acceptance ⑤ measures.
        """
        offset = self._frames.lift_offset_world(side, self._q_lift)
        return make_pose(pose_position(pose_world) - offset, pose_quat(pose_world))

    # -- state -------------------------------------------------------------------

    @property
    def stopped(self) -> bool:
        """Return whether the jog is latched stopped (cleared by ``resume``)."""
        return self._stopped

    @property
    def stop_reason(self) -> JogStopReason | None:
        """Return the reason the jog last stopped, or None when running."""
        return self._stop_reason

    @property
    def steps_committed(self) -> int:
        """Return how many steps advanced the committed pose."""
        return self._steps_committed

    @property
    def steps_held(self) -> int:
        """Return how many steps held instead of advancing (never silently skipped)."""
        return self._steps_held

    def resume(self) -> None:
        """Clear the latched stop so jogging may continue."""
        self._stopped = False
        self._stop_reason = None

    def committed_solution(self) -> np.ndarray:
        """Return a copy of the committed float[16] arm state."""
        return self._committed.copy()

    def seed(self, values16: np.ndarray) -> None:
        """Seed the committed state and the IK config from a driver-state vector.

        Set at connect from the robot's actual joint state so the first jog builds on
        where the arm really is, not the home keyframe. Clears any latched stop.
        """
        values = np.asarray(values16, dtype=float)
        if values.shape[0] != BIMANUAL_WIDTH:
            raise ValueError(f"seed must be {BIMANUAL_WIDTH}-dim, got {values.shape[0]}")
        self._committed = values.copy()
        self._adapter.sync(self._committed)
        self.resume()

    def arm_joints(self, side: str) -> np.ndarray:
        """Return the committed seven arm-joint angles (radians) for WP-2D-02's Jacobian."""
        base = 0 if side == "right" else SIDE_WIDTH
        return self._committed[base : base + ARM_JOINTS_PER_SIDE].copy()

    def current_pose(
        self, side: str, frame: ReferenceFrame | None = None, tcp: TcpSelection | None = None
    ) -> np.ndarray:
        """Return the current TCP pose, in the physical world or expressed in a frame."""
        frame = frame if frame is not None else self._reference_frame
        tcp = tcp if tcp is not None else self._default_tcp
        world = self._tcp_world(side, tcp)
        return self._world_to_frame(side, world, frame)

    # -- jog and move ------------------------------------------------------------

    def step(self, command: JogCommand) -> JogResult:
        """Run one jog step; commit on success, else hold and latch the jog stopped."""
        if self._stopped:
            return self._held_result(self._stop_reason, None, detail="jog is latched stopped")

        side = _require_side(command.side)
        tcp = command.tcp
        current_world = self._tcp_world(side, tcp)
        target_world = self._apply_delta(side, current_world, command)

        monitored = self._monitor_singularity(side, target_world)
        if monitored is not None:
            return monitored

        outcome = self._solve_to_tcp_target(side, target_world, tcp)
        if outcome.held:
            reason = _reason_from_faults(outcome.faults)
            return self._hold(reason, outcome, target_world)

        violations = _mechanical_limit_violations(outcome.solution_rad)
        if violations:
            return self._hold(
                JogStopReason.LIMIT,
                outcome,
                target_world,
                detail="committed solution left the canonical mechanical limits: "
                + ", ".join(violations),
            )

        return self._commit(side, outcome, target_world, tcp)

    def plan_pose(
        self,
        side: str,
        target_pose: np.ndarray,
        frame: ReferenceFrame | None = None,
        tcp: TcpSelection | None = None,
        commit: bool = True,
    ) -> JogResult:
        """Move to (or, with ``commit=False``, IK-existence-check) an absolute TCP pose.

        WP-2D-09's numeric Move-to calls this with ``commit=False`` to prove a solution
        exists before executing, then ``commit=True`` to run it. A non-committing check
        restores the arm state afterward, so the probe never moves the committed pose.
        """
        side = _require_side(side)
        frame = frame if frame is not None else self._reference_frame
        tcp = tcp if tcp is not None else self._default_tcp
        if commit and self._stopped:
            return self._held_result(self._stop_reason, None, detail="jog is latched stopped")

        target_world = self._frame_to_world(side, np.asarray(target_pose, dtype=float), frame)
        outcome, reached = self._converge_to_tcp_target(side, target_world, tcp)

        if not commit:
            self._adapter.sync(self._committed)
            if outcome.held:
                return self._held_result(
                    _reason_from_faults(outcome.faults),
                    outcome,
                    target_world,
                    detail="no admissible IK solution for the requested pose",
                )
            if not reached:
                return self._held_result(
                    JogStopReason.NO_SOLUTION,
                    outcome,
                    target_world,
                    detail="target unreachable: solver did not converge within budget",
                )
            return JogResult(
                committed=False,
                stopped=False,
                reason=None,
                accepted=outcome.accepted,
                solution_rad=outcome.solution_rad,
                target_world=target_world,
                achieved_world=self._achieved_tcp_world(side, outcome.solution_rad, tcp),
                fallback_fired=_fallback_fired(outcome.faults),
                detail="IK solution exists for the requested pose",
            )

        if outcome.held:
            return self._hold(_reason_from_faults(outcome.faults), outcome, target_world)
        if not reached:
            return self._hold(
                JogStopReason.NO_SOLUTION,
                outcome,
                target_world,
                detail="target unreachable: solver did not converge within budget",
            )
        violations = _mechanical_limit_violations(outcome.solution_rad)
        if violations:
            return self._hold(
                JogStopReason.LIMIT,
                outcome,
                target_world,
                detail="solution left the canonical mechanical limits: " + ", ".join(violations),
            )
        return self._commit(side, outcome, target_world, tcp)

    def ik_solution_exists(
        self,
        side: str,
        target_pose: np.ndarray,
        frame: ReferenceFrame | None = None,
        tcp: TcpSelection | None = None,
    ) -> bool:
        """Return whether an admissible IK solution exists for an absolute TCP pose."""
        return not self.plan_pose(side, target_pose, frame, tcp, commit=False).stopped

    # -- internals ---------------------------------------------------------------

    def _apply_delta(self, side: str, current_world: np.ndarray, command: JogCommand) -> np.ndarray:
        """Apply the command's frame-local delta to the current TCP world pose."""
        unit = _AXIS_UNIT[command.axis.value] * float(command.sign)
        position = pose_position(current_world)
        quat = pose_quat(current_world)

        if command.kind is JogKind.TRANSLATION:
            magnitude = self._translation_step_m * self._velocity_scale
            axis_world = self._axis_in_world(side, unit, quat, command.frame)
            return make_pose(position + magnitude * axis_world, quat)

        magnitude = self._rotation_step_rad * self._velocity_scale
        if command.frame is ReferenceFrame.TOOL:
            # Rotate about the tool's own axis: post-multiply keeps the axis body-fixed.
            delta = axis_angle_to_quat(unit, magnitude)
            return make_pose(position, quat_mul(quat, delta))
        # World and base share orientation here, so both rotate about the world axis.
        delta = axis_angle_to_quat(unit, magnitude)
        return make_pose(position, quat_mul(delta, quat))

    def _axis_in_world(
        self, side: str, unit: np.ndarray, tcp_quat: np.ndarray, frame: ReferenceFrame
    ) -> np.ndarray:
        """Return a frame-local unit axis expressed in the world frame."""
        if frame is ReferenceFrame.TOOL:
            return rotate_vec(tcp_quat, unit)
        if frame is ReferenceFrame.BASE:
            base_quat = pose_quat(self._frames.world_from_base(side, self._q_lift))
            return rotate_vec(base_quat, unit)
        return unit

    def _prepare_ik_targets(self, side: str, target_world: np.ndarray, tcp: TcpSelection) -> None:
        """Set both arms' IK targets: the jogged side to its new TCP, the other held."""
        offset = self._tcp.offset(side, tcp)
        control_world = compose_pose(target_world, invert_pose(offset))
        control_ik = self.reflect_world_to_ik(side, control_world)
        self._adapter.set_target(side, control_ik)
        for other in SIDES:
            if other != side:
                self._adapter.set_target(other, self._control_point_ik(other))

    def _solve_to_tcp_target(
        self, side: str, target_world: np.ndarray, tcp: TcpSelection
    ) -> IkOutcome:
        """Run one differential solve cycle toward a TCP target (the jog-step primitive)."""
        self._prepare_ik_targets(side, target_world, tcp)
        return self._adapter.solve()

    def _converge_to_tcp_target(
        self, side: str, target_world: np.ndarray, tcp: TcpSelection
    ) -> tuple[IkOutcome, bool]:
        """Drive the differential solver to a TCP target; return the last outcome + reached.

        A jog step is one cycle, but an absolute Move-to and its IK-existence probe must
        converge, so this iterates the persistent solver until the achieved TCP is within
        tolerance, a hold fires, or the cycle budget is spent (an unreachable pose).
        """
        self._prepare_ik_targets(side, target_world, tcp)
        outcome = self._adapter.solve()
        for _ in range(MOVE_TO_MAX_CYCLES):
            if outcome.held:
                return outcome, False
            if self._reached(side, outcome.solution_rad, target_world, tcp):
                return outcome, True
            outcome = self._adapter.solve()
        return outcome, not outcome.held and self._reached(
            side, outcome.solution_rad, target_world, tcp
        )

    def _reached(
        self,
        side: str,
        solution_rad: np.ndarray | None,
        target_world: np.ndarray,
        tcp: TcpSelection,
    ) -> bool:
        """Report whether a solution's TCP is within Move-to tolerance of the target."""
        if solution_rad is None:
            return False
        achieved = self._achieved_tcp_world(side, solution_rad, tcp)
        if float(np.linalg.norm(pose_position(achieved) - pose_position(target_world))) > (
            MOVE_TO_TOLERANCE_M
        ):
            return False
        return quat_geodesic_angle(pose_quat(achieved), pose_quat(target_world)) <= (
            MOVE_TO_TOLERANCE_RAD
        )

    def _achieved_tcp_world(
        self, side: str, solution_rad: np.ndarray, tcp: TcpSelection
    ) -> np.ndarray:
        """Return the physical-world TCP pose implied by a raw radian solution."""
        control_world = self._frames.control_point_pose(side, solution_rad, self._q_lift)
        return compose_pose(control_world, self._tcp.offset(side, tcp))

    def _control_point_ik(self, side: str) -> np.ndarray:
        """Return the committed control-point pose in the IK world (base at lift zero)."""
        return self._frames.control_point_pose(side, self._committed, 0.0)

    def _tcp_world(self, side: str, tcp: TcpSelection) -> np.ndarray:
        """Return the committed TCP pose in the physical world (base at current lift)."""
        control_world = self._frames.control_point_pose(side, self._committed, self._q_lift)
        return compose_pose(control_world, self._tcp.offset(side, tcp))

    def _frame_to_world(
        self, side: str, pose_in_frame: np.ndarray, frame: ReferenceFrame
    ) -> np.ndarray:
        """Express a pose given in a reference frame as a physical-world pose."""
        if frame is ReferenceFrame.WORLD:
            return pose_in_frame
        if frame is ReferenceFrame.BASE:
            return compose_pose(self._frames.world_from_base(side, self._q_lift), pose_in_frame)
        return compose_pose(self._tcp_world(side, self._default_tcp), pose_in_frame)

    def _world_to_frame(
        self, side: str, pose_world: np.ndarray, frame: ReferenceFrame
    ) -> np.ndarray:
        """Express a physical-world pose in a reference frame."""
        if frame is ReferenceFrame.WORLD:
            return pose_world
        if frame is ReferenceFrame.BASE:
            inverse_base = invert_pose(self._frames.world_from_base(side, self._q_lift))
            return compose_pose(inverse_base, pose_world)
        return compose_pose(invert_pose(self._tcp_world(side, self._default_tcp)), pose_world)

    def _monitor_singularity(self, side: str, target_world: np.ndarray) -> JogResult | None:
        """Consult an installed WP-2D-02 monitor; hold on a truthy reason string."""
        if self._singularity_monitor is None:
            return None
        detail = self._singularity_monitor(side, self.arm_joints(side))
        if not detail:
            return None
        self._stopped = True
        self._stop_reason = JogStopReason.SINGULARITY
        self._steps_held += 1
        return self._held_result(JogStopReason.SINGULARITY, None, target_world, detail=str(detail))

    def _commit(
        self, side: str, outcome: IkOutcome, target_world: np.ndarray, tcp: TcpSelection
    ) -> JogResult:
        """Advance the committed pose to the accepted solution and report success."""
        self._committed = np.asarray(outcome.solution_rad, dtype=float).copy()
        self._steps_committed += 1
        achieved = self._tcp_world(side, tcp)
        return JogResult(
            committed=True,
            stopped=False,
            reason=None,
            accepted=outcome.accepted,
            solution_rad=outcome.solution_rad,
            target_world=target_world,
            achieved_world=achieved,
            fallback_fired=_fallback_fired(outcome.faults),
        )

    def _hold(
        self,
        reason: JogStopReason,
        outcome: IkOutcome,
        target_world: np.ndarray,
        detail: str = "",
    ) -> JogResult:
        """Latch the jog stopped without moving, and report the categorized reason."""
        self._stopped = True
        self._stop_reason = reason
        self._steps_held += 1
        return self._held_result(reason, outcome, target_world, detail=detail)

    def _held_result(
        self,
        reason: JogStopReason | None,
        outcome: IkOutcome | None,
        target_world: np.ndarray | None = None,
        detail: str = "",
    ) -> JogResult:
        """Build a held ``JogResult`` that keeps the committed pose in place."""
        faults = outcome.faults if outcome is not None else ()
        accepted = outcome.accepted if outcome is not None else None
        return JogResult(
            committed=False,
            stopped=True,
            reason=reason,
            accepted=accepted,
            solution_rad=None,
            target_world=target_world,
            achieved_world=None,
            faults=faults,
            fallback_fired=_fallback_fired(faults),
            detail=detail,
        )


def _require_side(side: str) -> str:
    """Return ``side`` if it is a valid arm, else reject."""
    if side not in SIDES:
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    return side


def _reason_from_faults(faults: tuple[IkFault, ...]) -> JogStopReason:
    """Reduce a held cycle's faults to the single highest-priority stop reason."""
    present = {_REASON_BY_CODE[fault.code] for fault in faults if fault.code in _REASON_BY_CODE}
    for reason in _REASON_PRIORITY:
        if reason in present:
            return reason
    return JogStopReason.NO_SOLUTION


def _fallback_fired(faults: tuple[IkFault, ...]) -> bool:
    """Return whether any unconstrained-fallback fault is present."""
    return any(fault.code is IkFaultCode.UNCONSTRAINED_FALLBACK for fault in faults)


def _mechanical_limit_violations(solution_rad: np.ndarray | None) -> list[str]:
    """Return per-joint messages for any committed value outside the canonical limits.

    The redundant first-line-of-defense check (02b §4.3): even after the adapter clamp,
    the committed solution is re-verified against the canonical mechanical limits (the
    overridden jnt_range = LeRobot soft limits) before the jog advances.
    """
    if solution_rad is None:
        return []
    values = np.asarray(solution_rad, dtype=float)
    messages: list[str] = []
    for slot, limit in enumerate(all_soft_limits()):
        if slot >= values.shape[0]:
            break
        value = float(values[slot])
        low = limit.lower_rad.value - _MECHANICAL_LIMIT_TOLERANCE_RAD
        high = limit.upper_rad.value + _MECHANICAL_LIMIT_TOLERANCE_RAD
        if value < low or value > high:
            messages.append(f"{limit.mjcf_joint}={value:.4f} rad")
    return messages


def build_cartesian_jog(
    xml: str | None = None,
    mode: str = "bimanual",
    ik_params: IKParams | None = None,
    allow_unconstrained_fallback: bool = False,
    residual_max_m: float | None = None,
    reference_frame: ReferenceFrame = ReferenceFrame.WORLD,
    tcp: TcpSelection = TcpSelection.FLANGE,
    q_lift: float = 0.0,
) -> CartesianJog:
    """Build a Cartesian jog over the ordered-build IK adapter (the sanctioned entry).

    The IK adapter is built through ``sim.ik.build_ik_adapter``, so the FR-SIM-080
    order (ArmSetup → jnt_range override → Kinematics) and the fallback-off default are
    inherited, not re-established. There is no path through this factory to a Kinematics
    whose limits predate the override.

    Args:
        xml: MJCF path; None uses the WP-0C-03 fixed cell asset.
        mode: ``"right"``, ``"left"``, or ``"bimanual"``.
        ik_params: mink IK parameters; None uses ``openarm_control`` defaults.
        allow_unconstrained_fallback: Whether the ``limits=[]`` retry may run (default
            False — FR-SAF-016).
        residual_max_m: EE residual threshold in metres, or None to leave it uncalibrated.
        reference_frame: Default reference frame for a command that omits one.
        tcp: Default TCP selection (FLANGE — the flange, not the grasp point).
        q_lift: Initial lifter height in metres, clamped to the model's travel.

    Returns:
        (CartesianJog) A ready jog seeded to the home pose.
    """
    resolved_params = ik_params if ik_params is not None else IKParams()
    adapter = build_ik_adapter(
        xml=xml,
        mode=mode,
        ik_params=resolved_params,
        allow_unconstrained_fallback=allow_unconstrained_fallback,
        residual_max_m=residual_max_m,
    )
    frames = KinematicFrames(xml=xml)
    tool = ToolCenterPoint(frames)
    return CartesianJog(
        adapter=adapter,
        frames=frames,
        tcp=tool,
        ik_params=resolved_params,
        reference_frame=reference_frame,
        default_tcp=tcp,
        q_lift=q_lift,
        xml=xml,
        mode=mode,
    )
