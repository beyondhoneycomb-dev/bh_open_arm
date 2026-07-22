"""The safety filter behind the single send_action gateway (`WP-1-03`).

`11` NFR-INF-008 makes one place — the `OaOpenArmFollower.send_action()` override —
the sole, un-bypassable enforcement point. This module is the filter that override
runs. It is deliberately data-in, decision-out and holds no CAN handle: it turns a
producer's `RequestedPositionAction` into either an `AcceptedPositionAction` (with a
`SafetyOverride` recording every clamp) or a rejection carrying one distinct reason
code. The gateway (`backend.actuation.enforcement`) is what wires it to the single
CAN writer; the guard (`backend.actuation.guard`) is what feeds it the fail-closed
latch. Nothing here writes the bus.

The eight checks run in one fixed order (`12` FR-SAF-074: unit -> zero -> limit
(2-stage) -> freshness -> workspace/collision -> slew -> jerk -> stopped -> CAN).
Order is enforced, not assumed: `evaluate` refuses a shuffled order rather than
silently running the checks in whatever sequence a caller passed, because a filter
that clamps position before it has confirmed the source is fresh is a different, and
unsafe, filter (acceptance ④).

Two behaviours the checks must keep distinct (`03` FR-MOT-038, acceptance ⑨):

- A joint-position-limit or workspace-wall violation **clips and proceeds**
  (`JointPosChecker`, `force_stop=False`): the command is admitted at the clamped
  value and the clamp is recorded.
- A step-delta, velocity, acceleration or jerk violation **stops immediately**
  (`JointDeltaPosChecker`): no motion is admitted; the tick holds.

The rate guards are three independent parameters, never one (`14` FR-OPS-012): the
step-delta jump guard (`max_relative_target`) is not a velocity limit, and a config
that leaves velocity or acceleration unset in the belief the jump guard covers them
is refused at validation time (acceptance ⑥).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from contracts.action import ClampReason, SafetyOverride
from contracts.units import Deg, Nm, Rad, clamp_torque, deg_to_rad

# MIT stiffness/damping gain envelope (`03` FR-MOT-018): the CAN packet carries kp
# in a 12-bit field scaled to [0,500] and kd to [0,5]; a value outside the range is
# silently wrapped by the encoder, so it is validated and rejected before it is sent
# rather than let a wrapped gain reach a motor.
KP_MIN = 0.0
KP_MAX = 500.0
KD_MIN = 0.0
KD_MAX = 5.0

# A commanded position within this many radians of the present one counts as "not
# moving" for the stopped-state check. It is a numerical-equality tolerance, not a
# motion budget: STOP_HOLD admits a hold at present, and only a hold.
STOPPED_EPSILON_RAD = 1e-6


class SafetyReason(Enum):
    """The finer cause a check fired — one distinct value per check (acceptance ③).

    A merged "rejected" code is forbidden: an audit that cannot tell a stale source
    from a jerk violation cannot attribute a hold. Each of the eight ordered checks
    contributes at least one reason, and the config-time and gain checks add their
    own, so a fixture that triggers any single check gets back exactly which one.
    """

    NONE = "none"
    UNIT_MISMATCH = "unit_mismatch"
    ZERO_UNCALIBRATED = "zero_uncalibrated"
    JOINT_LIMIT = "joint_limit"
    STALE_SOURCE = "stale_source"
    WORKSPACE_WALL = "workspace_wall"
    COLLISION_LATCH = "collision_latch"
    VELOCITY_LIMIT = "velocity_limit"
    STEP_DELTA = "step_delta"
    ACCEL_LIMIT = "accel_limit"
    JERK_LIMIT = "jerk_limit"
    NOT_STOPPED = "not_stopped"
    ORDER_VIOLATION = "order_violation"
    # Config- and gain-time reasons: raised before or around the ordered pipeline.
    OPERATIONAL_NOT_SUBSET = "operational_not_subset"
    TORQUE_EXCEEDS_PEAK = "torque_exceeds_peak"
    MERGED_RATE_GUARD = "merged_rate_guard"
    KP_OUT_OF_RANGE = "kp_out_of_range"
    KD_OUT_OF_RANGE = "kd_out_of_range"


class CheckStage(Enum):
    """The eight ordered checks the gateway runs before any CAN call (`12` FR-SAF-074)."""

    UNIT = "unit"
    ZERO = "zero"
    LIMIT = "limit"
    FRESHNESS = "freshness"
    WORKSPACE_COLLISION = "workspace_collision"
    SLEW = "slew"
    JERK = "jerk"
    STOPPED = "stopped"


# The canonical order. `evaluate` runs exactly this sequence and rejects any other
# (acceptance ④): the order is the contract, not an implementation detail.
CHECK_ORDER: tuple[CheckStage, ...] = (
    CheckStage.UNIT,
    CheckStage.ZERO,
    CheckStage.LIMIT,
    CheckStage.FRESHNESS,
    CheckStage.WORKSPACE_COLLISION,
    CheckStage.SLEW,
    CheckStage.JERK,
    CheckStage.STOPPED,
)


class SafetyConfigError(ValueError):
    """Raised when a `SafetyLimits` set is internally inconsistent (config-time).

    Attributes:
        reason: The distinct config reason, so a caller can assert which rule bit.
    """

    def __init__(self, reason: SafetyReason, message: str) -> None:
        """Build a config error carrying its reason code.

        Args:
            reason: The config reason (subset/torque/merged-rate).
            message: Human-readable description.
        """
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class SafetyLimits:
    """The clamp envelope the filter enforces — passed in, never invented here.

    Every bound belongs to the gateway/calibration owner, so the filter holds none
    of its own: a `SafetyLimits` is constructed with the mechanical URDF limits, the
    tighter operational limits, the three independent rate guards, the jerk limit,
    and the physical peak torque, and `validate` refuses a set that contradicts the
    two-stage clamp (`03` FR-MOT-030/032) or collapses the rate guards.

    All position/velocity/torque tuples are the full command width (16-dim
    bimanual); the follower tiles its per-side single-arm values before constructing
    one of these, so the filter itself is arm-structure-agnostic.

    Attributes:
        mechanical_deg: Per-joint mechanical URDF limit `(low, high)` in degrees.
        operational_deg: Per-joint operational limit `(low, high)`; must be a subset
            of the mechanical limit on every joint (`03` FR-MOT-032).
        velocity_limit_rad_s: Per-joint velocity ceiling (`12` §2.5 / URDF).
        accel_limit_rad_s2: Per-joint acceleration ceiling — a separate parameter
            from velocity (`14` FR-OPS-012).
        jerk_limit_rad_s3: Per-joint jerk ceiling (`01` FR-SYS-017).
        step_delta_limit_rad: Per-joint step-delta jump guard, radians per step —
            NOT a velocity limit (`03` FR-MOT-036), a third separate parameter.
        peak_torque_nm: Per-joint physical Peak Torque (`03` FR-MOT-037), the axis a
            torque clamp uses — never the packet-scale T_MAX.
        operational_torque_nm: Per-joint operational torque ceiling; must not exceed
            the physical peak on any joint.
    """

    mechanical_deg: tuple[tuple[Deg, Deg], ...]
    operational_deg: tuple[tuple[Deg, Deg], ...]
    velocity_limit_rad_s: tuple[float, ...] | None
    accel_limit_rad_s2: tuple[float, ...] | None
    jerk_limit_rad_s3: tuple[float, ...] | None
    step_delta_limit_rad: tuple[float, ...] | None
    peak_torque_nm: tuple[Nm, ...]
    operational_torque_nm: tuple[Nm, ...]

    @property
    def width(self) -> int:
        """The command width these limits are declared for.

        Returns:
            (int) The number of joints, from the mechanical-limit tuple length.
        """
        return len(self.mechanical_deg)

    def validate(self) -> None:
        """Reject a limit set that contradicts the two-stage clamp or merges guards.

        Raises:
            SafetyConfigError: With `OPERATIONAL_NOT_SUBSET` when an operational
                position or torque limit is not contained in the mechanical/peak
                envelope, `TORQUE_EXCEEDS_PEAK` when an operational torque exceeds
                the physical peak, or `MERGED_RATE_GUARD` when velocity, accel or
                the step-delta jump guard is left unset (the jump guard is not a
                velocity limit, so one cannot stand in for another).
        """
        self._validate_operational_subset()
        self._validate_torque_within_peak()
        self._validate_rate_guards_separate()

    def _validate_operational_subset(self) -> None:
        """Refuse an operational position limit wider than the mechanical one."""
        for index, (mechanical, operational) in enumerate(
            zip(self.mechanical_deg, self.operational_deg, strict=True)
        ):
            mech_low, mech_high = mechanical
            op_low, op_high = operational
            if op_low.value < mech_low.value or op_high.value > mech_high.value:
                raise SafetyConfigError(
                    SafetyReason.OPERATIONAL_NOT_SUBSET,
                    f"operational limit {operational} on joint {index} is not a subset of the "
                    f"mechanical limit {mechanical}; a save with a wider operational envelope is "
                    f"refused (03 FR-MOT-032)",
                )

    def _validate_torque_within_peak(self) -> None:
        """Refuse an operational torque limit above the physical Peak Torque."""
        for index, (peak, operational) in enumerate(
            zip(self.peak_torque_nm, self.operational_torque_nm, strict=True)
        ):
            if abs(operational.value) > abs(peak.value):
                raise SafetyConfigError(
                    SafetyReason.TORQUE_EXCEEDS_PEAK,
                    f"operational torque {operational} on joint {index} exceeds the physical "
                    f"Peak Torque {peak}; a torque clamp is bounded by Peak Torque, not the "
                    f"packet-scale T_MAX (03 FR-MOT-037)",
                )

    def _validate_rate_guards_separate(self) -> None:
        """Refuse a config that leaves any of the three rate guards unset."""
        missing = [
            name
            for name, value in (
                ("velocity_limit_rad_s", self.velocity_limit_rad_s),
                ("accel_limit_rad_s2", self.accel_limit_rad_s2),
                ("step_delta_limit_rad", self.step_delta_limit_rad),
            )
            if value is None
        ]
        if missing:
            raise SafetyConfigError(
                SafetyReason.MERGED_RATE_GUARD,
                f"rate guards {missing} are unset; velocity, acceleration and the step-delta jump "
                f"guard are three independent parameters — the jump guard is not a velocity limit "
                f"(14 FR-OPS-012)",
            )


@dataclass(frozen=True)
class MotionHistory:
    """The motion state the rate checks difference against.

    Attributes:
        present_deg: Present joint positions this command departs from, degrees.
        prev_velocity_rad_s: Velocity command applied on the previous tick, or None
            at the first command after torque-on (treated as zero).
        prev_accel_rad_s2: Acceleration applied on the previous tick, or None.
    """

    present_deg: tuple[Deg, ...]
    prev_velocity_rad_s: tuple[float, ...] | None
    prev_accel_rad_s2: tuple[float, ...] | None


@dataclass(frozen=True)
class FilterInput:
    """One send_action's decision inputs, snapshotted so the filter stays pure.

    The request and present state are plain degree vectors of the follower's own
    width — 8 for a single arm, 16 for the bimanual — not the fixed-16 CTR-ACT
    channel type, because the enforcement point is a single arm's `send_action`
    (`11` NFR-INF-008) and the bimanual is assembled from two of them. The CTR-ACT
    `RequestedPositionAction`/`AcceptedPositionAction` are the bimanual dataset/audit
    channels, produced at that boundary, not inside the filter.

    Attributes:
        request: The producer's pre-clamp position request, degrees.
        history: The motion state the rate checks difference against.
        dt_sec: The control period the rate checks divide by.
        source_age_sec: Age of the source target against the freshness window.
        freshness_window_sec: Age past which the source is stale.
        calibrated: Whether the arm has a completed zero (`WP-1-02`).
        collision_latched: Whether the collision guard has latched fail-closed.
        require_stopped: Whether a soft stop (STOP_HOLD) is in effect — only a hold
            at present is admissible while it is.
        feedforward_torque_nm: Optional per-joint feed-forward torque routed to the
            MIT frame (`12` §2.7.0 tau release); clamped by Peak Torque here.
    """

    request: tuple[Deg, ...]
    history: MotionHistory
    dt_sec: float
    source_age_sec: float
    freshness_window_sec: float
    calibrated: bool
    collision_latched: bool
    require_stopped: bool
    feedforward_torque_nm: tuple[Nm, ...] | None


@dataclass(frozen=True)
class FilterOutcome:
    """What the filter decided for one command.

    Attributes:
        accepted: The admitted, clamped position vector, or None when a check
            stopped it (a degree vector of the follower's width).
        rejected: True when a stop-class check fired (no motion admitted).
        reason: The decisive reason — the first stop reason, else the first clamp
            reason, else NONE.
        stage: The stage that produced `reason`, or None on a clean pass.
        override: The audit record of whether and why the request was altered.
        feedforward_torque_nm: The peak-clamped feed-forward torque, one per joint.
    """

    accepted: tuple[Deg, ...] | None
    rejected: bool
    reason: SafetyReason
    stage: CheckStage | None
    override: SafetyOverride
    feedforward_torque_nm: tuple[Nm, ...]


# One check's internal result: whether it stopped the command, an optional reason
# and stage, and the working positions after any clip-and-proceed clamp.
@dataclass(frozen=True)
class _StepResult:
    stop: bool
    reason: SafetyReason
    stage: CheckStage | None
    working_deg: tuple[Deg, ...]
    clamped: bool


class SafetyFilter:
    """The ordered eight-check filter the single gateway runs (`12` FR-SAF-074).

    Ownership: holds only the limit envelope, which it does not own — the limits are
    passed in at construction. It holds no CAN handle and no producer; it is a pure
    decision function the gateway calls, and the gateway is the only thing that turns
    its decision into a bus write.
    """

    def __init__(self, limits: SafetyLimits) -> None:
        """Bind the filter to a validated limit envelope.

        Args:
            limits: The clamp envelope; `validate` is run here so a filter can never
                be constructed around a self-contradicting limit set.

        Raises:
            SafetyConfigError: If the limit envelope is inconsistent.
        """
        limits.validate()
        self._limits = limits

    @property
    def limits(self) -> SafetyLimits:
        """The validated limit envelope this filter enforces."""
        return self._limits

    def evaluate(
        self,
        state: FilterInput,
        check_order: tuple[CheckStage, ...] = CHECK_ORDER,
    ) -> FilterOutcome:
        """Run the eight checks in the mandated order and return one decision.

        Args:
            state: The command's snapshotted decision inputs.
            check_order: The order to run the checks in; defaults to the canonical
                order and is rejected if it differs (acceptance ④).

        Returns:
            (FilterOutcome) The single decision — accepted-and-clamped, or a stop
            carrying the one reason code of the check that fired.
        """
        if check_order != CHECK_ORDER:
            return self._stop(state, SafetyReason.ORDER_VIOLATION, None)

        feedforward = self._clamp_feedforward(state.feedforward_torque_nm)
        working = state.request
        first_clamp: tuple[SafetyReason, CheckStage] | None = None
        for stage in check_order:
            result = self._run_stage(stage, working, state)
            working = result.working_deg
            if result.stop:
                return FilterOutcome(
                    accepted=None,
                    rejected=True,
                    reason=result.reason,
                    stage=result.stage,
                    override=_override(active=True, reason=result.reason, stale=_is_stale(result)),
                    feedforward_torque_nm=feedforward,
                )
            if result.clamped and first_clamp is None and result.stage is not None:
                first_clamp = (result.reason, result.stage)

        decisive_reason: SafetyReason = SafetyReason.NONE
        decisive_stage: CheckStage | None = None
        if first_clamp is not None:
            decisive_reason, decisive_stage = first_clamp
        return FilterOutcome(
            accepted=working,
            rejected=False,
            reason=decisive_reason,
            stage=decisive_stage,
            override=_override(
                active=first_clamp is not None,
                reason=decisive_reason,
                stale=False,
            ),
            feedforward_torque_nm=feedforward,
        )

    def _run_stage(
        self, stage: CheckStage, working: tuple[Deg, ...], state: FilterInput
    ) -> _StepResult:
        """Dispatch one stage. A total map so an added stage cannot be silently skipped."""
        if stage is CheckStage.UNIT:
            return self._check_unit(working, state)
        if stage is CheckStage.ZERO:
            return self._check_zero(working, state)
        if stage is CheckStage.LIMIT:
            return self._check_limit(working)
        if stage is CheckStage.FRESHNESS:
            return self._check_freshness(working, state)
        if stage is CheckStage.WORKSPACE_COLLISION:
            return self._check_workspace_collision(working, state)
        if stage is CheckStage.SLEW:
            return self._check_slew(working, state)
        if stage is CheckStage.JERK:
            return self._check_jerk(working, state)
        return self._check_stopped(working, state)

    def _check_unit(self, working: tuple[Deg, ...], state: FilterInput) -> _StepResult:
        """Reject a command whose width or feed-forward width is wrong (unit shape)."""
        if len(working) != self._limits.width:
            return _stop_step(SafetyReason.UNIT_MISMATCH, CheckStage.UNIT, working)
        torque = state.feedforward_torque_nm
        if torque is not None and len(torque) != self._limits.width:
            return _stop_step(SafetyReason.UNIT_MISMATCH, CheckStage.UNIT, working)
        return _pass_step(working)

    def _check_zero(self, working: tuple[Deg, ...], state: FilterInput) -> _StepResult:
        """Reject a command when the arm has no established zero (`WP-1-02`)."""
        if not state.calibrated:
            return _stop_step(SafetyReason.ZERO_UNCALIBRATED, CheckStage.ZERO, working)
        return _pass_step(working)

    def _check_limit(self, working: tuple[Deg, ...]) -> _StepResult:
        """Clip a position to the operational limit and proceed (`03` FR-MOT-038)."""
        clamped: list[Deg] = []
        hit = False
        for angle, (low, high) in zip(working, self._limits.operational_deg, strict=True):
            bounded = Deg(min(max(angle.value, low.value), high.value))
            if bounded.value != angle.value:
                hit = True
            clamped.append(bounded)
        if hit:
            return _clamp_step(SafetyReason.JOINT_LIMIT, CheckStage.LIMIT, tuple(clamped))
        return _pass_step(working)

    def _check_freshness(self, working: tuple[Deg, ...], state: FilterInput) -> _StepResult:
        """Reject a source older than the freshness window."""
        if state.source_age_sec > state.freshness_window_sec:
            return _stop_step(SafetyReason.STALE_SOURCE, CheckStage.FRESHNESS, working)
        return _pass_step(working)

    def _check_workspace_collision(
        self, working: tuple[Deg, ...], state: FilterInput
    ) -> _StepResult:
        """Latch fail-closed on an active collision; otherwise pass (walls clip in LIMIT).

        The workspace virtual walls are expressed as operational position limits and
        are enforced in the LIMIT stage as clip-and-proceed; what is decisive here is
        the collision guard's fail-closed latch, which stops the command outright and
        never itself writes the bus (`12` FR-SAF-074 ③).
        """
        if state.collision_latched:
            return _stop_step(SafetyReason.COLLISION_LATCH, CheckStage.WORKSPACE_COLLISION, working)
        return _pass_step(working)

    def _check_slew(self, working: tuple[Deg, ...], state: FilterInput) -> _StepResult:
        """Stop on a step-delta jump or a velocity-limit breach (two separate guards)."""
        present_rad = _to_rad(state.history.present_deg)
        working_rad = _to_rad(working)
        deltas = [abs((w - p).value) for w, p in zip(working_rad, present_rad, strict=True)]
        step_delta = self._limits.step_delta_limit_rad
        if step_delta is not None and any(
            delta > limit for delta, limit in zip(deltas, step_delta, strict=True)
        ):
            return _stop_step(SafetyReason.STEP_DELTA, CheckStage.SLEW, working)
        velocity_limit = self._limits.velocity_limit_rad_s
        if velocity_limit is not None:
            velocities = [delta / state.dt_sec for delta in deltas]
            if any(vel > limit for vel, limit in zip(velocities, velocity_limit, strict=True)):
                return _stop_step(SafetyReason.VELOCITY_LIMIT, CheckStage.SLEW, working)
        return _pass_step(working)

    def _check_jerk(self, working: tuple[Deg, ...], state: FilterInput) -> _StepResult:
        """Stop on an acceleration or jerk breach (higher-order rate guards).

        Acceleration and jerk are differences against prior motion, so at a cold start
        (no prior velocity) there is no reference and neither is checked — the first
        move from rest is not an infinite acceleration, it is simply the first move.
        Jerk likewise waits until a prior acceleration exists (the second recorded
        move), so the guard fires on genuinely changing motion, not on the transient
        of having no history yet.
        """
        prev_velocity = state.history.prev_velocity_rad_s
        if prev_velocity is None:
            return _pass_step(working)
        present_rad = _to_rad(state.history.present_deg)
        working_rad = _to_rad(working)
        velocities = [
            (w - p).value / state.dt_sec for w, p in zip(working_rad, present_rad, strict=True)
        ]
        accels = [(v - pv) / state.dt_sec for v, pv in zip(velocities, prev_velocity, strict=True)]
        accel_limit = self._limits.accel_limit_rad_s2
        if accel_limit is not None and any(
            abs(a) > limit for a, limit in zip(accels, accel_limit, strict=True)
        ):
            return _stop_step(SafetyReason.ACCEL_LIMIT, CheckStage.JERK, working)
        prev_accel = state.history.prev_accel_rad_s2
        jerk_limit = self._limits.jerk_limit_rad_s3
        if prev_accel is not None and jerk_limit is not None:
            jerks = [(a - pa) / state.dt_sec for a, pa in zip(accels, prev_accel, strict=True)]
            if any(abs(j) > limit for j, limit in zip(jerks, jerk_limit, strict=True)):
                return _stop_step(SafetyReason.JERK_LIMIT, CheckStage.JERK, working)
        return _pass_step(working)

    def _check_stopped(self, working: tuple[Deg, ...], state: FilterInput) -> _StepResult:
        """While a soft stop holds, admit only a hold at present (`01` FR-SYS-017)."""
        if not state.require_stopped:
            return _pass_step(working)
        present_rad = _to_rad(state.history.present_deg)
        working_rad = _to_rad(working)
        if any(
            abs((w - p).value) > STOPPED_EPSILON_RAD
            for w, p in zip(working_rad, present_rad, strict=True)
        ):
            return _stop_step(SafetyReason.NOT_STOPPED, CheckStage.STOPPED, working)
        return _pass_step(working)

    def _clamp_feedforward(self, torque: tuple[Nm, ...] | None) -> tuple[Nm, ...]:
        """Clamp a feed-forward torque to Peak Torque, or return all-zero when absent.

        Args:
            torque: The requested per-joint feed-forward torque, or None.

        Returns:
            (tuple[Nm, ...]) The peak-clamped torque; a position-only command carries
            all-zero feed-forward (`10` FR-TRN-066).
        """
        if torque is None:
            return tuple(Nm(0.0) for _ in range(self._limits.width))
        return tuple(
            clamp_torque(value, peak)
            for value, peak in zip(torque, self._limits.peak_torque_nm, strict=True)
        )

    def _stop(
        self, state: FilterInput, reason: SafetyReason, stage: CheckStage | None
    ) -> FilterOutcome:
        """Build a stop outcome that admits no motion."""
        return FilterOutcome(
            accepted=None,
            rejected=True,
            reason=reason,
            stage=stage,
            override=_override(
                active=True, reason=reason, stale=reason is SafetyReason.STALE_SOURCE
            ),
            feedforward_torque_nm=self._clamp_feedforward(state.feedforward_torque_nm),
        )


def _to_rad(values: tuple[Deg, ...]) -> tuple[Rad, ...]:
    """Convert a degree tuple to radians through the one sanctioned crossing."""
    return tuple(deg_to_rad(value) for value in values)


def _pass_step(working: tuple[Deg, ...]) -> _StepResult:
    """A check that neither stopped nor clamped."""
    return _StepResult(
        stop=False, reason=SafetyReason.NONE, stage=None, working_deg=working, clamped=False
    )


def _stop_step(reason: SafetyReason, stage: CheckStage, working: tuple[Deg, ...]) -> _StepResult:
    """A check that stopped the command with a distinct reason."""
    return _StepResult(stop=True, reason=reason, stage=stage, working_deg=working, clamped=False)


def _clamp_step(reason: SafetyReason, stage: CheckStage, working: tuple[Deg, ...]) -> _StepResult:
    """A clip-and-proceed check that altered the command and recorded why."""
    return _StepResult(stop=False, reason=reason, stage=stage, working_deg=working, clamped=True)


def _is_stale(result: _StepResult) -> bool:
    """Whether a stopping result is the stale-source case."""
    return result.reason is SafetyReason.STALE_SOURCE


_REASON_TO_CLAMP = {
    SafetyReason.NONE: ClampReason.NONE,
    SafetyReason.JOINT_LIMIT: ClampReason.JOINT_LIMIT,
    SafetyReason.WORKSPACE_WALL: ClampReason.JOINT_LIMIT,
    SafetyReason.TORQUE_EXCEEDS_PEAK: ClampReason.TORQUE_LIMIT,
    SafetyReason.STALE_SOURCE: ClampReason.STALE_SOURCE,
    SafetyReason.COLLISION_LATCH: ClampReason.SAFETY_LATCH,
}


def _override(active: bool, reason: SafetyReason, stale: bool) -> SafetyOverride:
    """Build the `safetyOverride` audit record for one decision (`12` FR-SAF-074).

    Args:
        active: Whether the request was altered (clamped or stopped).
        reason: The decisive safety reason.
        stale: Whether the decisive cause was a stale source.

    Returns:
        (SafetyOverride) The audit record, with the reason mapped to a `ClampReason`.
    """
    return SafetyOverride(
        override_active=active,
        clamp_reason=_REASON_TO_CLAMP.get(
            reason, ClampReason.JOINT_LIMIT if active else ClampReason.NONE
        ),
        stale=stale,
        latched=reason is SafetyReason.COLLISION_LATCH,
    )
