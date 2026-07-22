"""Building the MIT command each reaction strategy sends — with the three safety guards.

This is where `12` §2.10's reaction table becomes real MIT frames, and where the three
rules that make those frames safe are enforced by construction rather than by comment:

- **`FR-SAF-069`** — the three feed-forward reactions are refused when the follower
  carries no torque/velocity channel (delegated to `capability.require_channels`).
- **`FR-SAF-040`** — a position command with `kd == 0` is refused, because Damiao's
  manual warns that position control with zero damping makes the motor vibrate or run
  away. GRAVITY_COMP's `(kp=0, kd=0)` is *not* a position command (its stiffness is
  zero), so it is exempt; returning to position control from it is the dangerous edge,
  and `resume_to_position` guards that crossing.
- **`FR-SAF-042`** — POWER_OFF is refused without a fall-warning acknowledgement *and*
  a separate confirmation (a genuine double confirm), because category 0 drops a
  brakeless arm.

A reaction is one of three shapes: a continuous-send MIT `batch` (STOP_HOLD,
GRAVITY_COMP, RETRACT, ADMITTANCE — the loop keeps sending it, `FR-SAF-038`/`073`), a
gated decel trajectory (STOP_DECEL — category 1, power removed only after a confirmed
stop), or a power-off `directive` (POWER_OFF — category 0). `τ_grav` is an *input* here,
not computed: it is the GMO/gravity model term (`WP-2B-02`/`WP-2C-01`) the reaction
carries through to the frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.reaction.capability import TorqueChannel, require_channels
from backend.reaction.constants import (
    ADMITTANCE_GAIN,
    POWER_OFF_CAN_OPCODE,
    POWER_OFF_FALL_WARNING,
    RETRACT_ALPHA_RAD,
    RETRACT_KP_LOW,
    STOP_DECEL_RAMP_STEPS,
)
from backend.reaction.strategy import ReactionStrategy, properties
from contracts.action import ExecutedMitCommand
from contracts.units import Nm, Rad, RadPerSec

# A commanded stiffness at or below this counts as "no position control": the position
# term is inert, so the `FR-SAF-040` kd≠0 rule does not apply to the frame. It is a
# numerical-zero tolerance on the MIT kp gain, not a tuning threshold.
KP_POSITION_CONTROL_EPSILON = 1e-9

# Zero feed-forward velocity/torque, reused where a strategy commands neither.
_ZERO_VELOCITY = RadPerSec(0.0)
_ZERO_TORQUE = Nm(0.0)


class KdZeroPositionCommandError(ValueError):
    """Raised when a position command carries `kd == 0` (`FR-SAF-040`).

    Attributes:
        joint_index: The joint whose command was a zero-damping position command.
    """

    def __init__(self, joint_index: int) -> None:
        """Build the refusal, naming the offending joint.

        Args:
            joint_index: Index of the joint commanding a position with zero damping.
        """
        super().__init__(
            f"joint {joint_index} commands a position with kd=0; Damiao position control with "
            f"zero damping vibrates or runs away, so it is refused (FR-SAF-040)"
        )
        self.joint_index = joint_index


class PowerOffConfirmationError(RuntimeError):
    """Raised when POWER_OFF is requested without the fall warning and double confirm."""


@dataclass(frozen=True)
class PowerOffConfirmation:
    """The two independent confirmations POWER_OFF requires (`FR-SAF-042`).

    Both must be set — the operator both acknowledges the fall warning and separately
    confirms the power cut — because category 0 drops a brakeless arm. Two fields, not
    one, so a single accidental click cannot arm a fall.

    Attributes:
        fall_warning_acknowledged: The operator saw and acknowledged the fall warning.
        confirmed: The operator then separately confirmed the power-off.
    """

    fall_warning_acknowledged: bool
    confirmed: bool

    @property
    def is_double_confirmed(self) -> bool:
        """Whether both independent confirmations are present.

        Returns:
            (bool) True only when the warning was acknowledged and then confirmed.
        """
        return self.fall_warning_acknowledged and self.confirmed


@dataclass(frozen=True)
class PowerOffDirective:
    """The category-0 power-cut a POWER_OFF reaction authorizes (`FR-SAF-042`).

    Expressed as the CAN broadcast opcode, not a `disable_torque()` call, so the
    reaction tree stays clear of the banned stop-path symbol (`04` NFR-MAN-002) while
    still naming the physical action. Carrying it as a directive (not executing it)
    also keeps the reaction layer decision-only, like the rest of the safety path.

    Attributes:
        can_opcode: The Damiao broadcast opcode for `disable_all()` (`0xFD`).
        warning: The fall warning that accompanied the double confirmation.
    """

    can_opcode: int
    warning: str


@dataclass(frozen=True)
class DecelTrajectory:
    """A category-1 controlled stop: decel frames, then a stop-gated power-off.

    The frames damp residual motion to rest at the hold pose (`kd` active); power is
    removed only after the caller confirms the arm has stopped, so a category-1 stop
    never falls before it has finished stopping.

    Attributes:
        frames: The position-hold frames sent while decelerating, one MIT batch each.
    """

    frames: tuple[tuple[ExecutedMitCommand, ...], ...]

    def authorize_power_off(self, stopped_confirmed: bool) -> PowerOffDirective:
        """Return the terminal power-off, only once the arm is confirmed stopped.

        Args:
            stopped_confirmed: Whether the arm has come to rest.

        Returns:
            (PowerOffDirective) The category-1 terminal power cut.

        Raises:
            PowerOffConfirmationError: If the stop is not yet confirmed — power is
                never removed mid-motion in a category-1 stop.
        """
        if not stopped_confirmed:
            raise PowerOffConfirmationError(
                "STOP_DECEL removes power only after the arm is confirmed stopped (category 1); "
                "a stop-first-then-power-off ordering never drops a moving arm"
            )
        return PowerOffDirective(can_opcode=POWER_OFF_CAN_OPCODE, warning=POWER_OFF_FALL_WARNING)


@dataclass(frozen=True)
class ReactionContext:
    """The pre-reaction motor state a reaction frame is built from.

    Every vector is one value per joint of the same width; `__post_init__` refuses a
    ragged context. `tau_grav` is the model gravity term computed upstream
    (`WP-2B-02`/`WP-2C-01`), carried through — the reaction layer does not compute it.
    `residual` is the per-joint GMO torque residual, whose direction RETRACT retreats
    against and whose magnitude ADMITTANCE yields along.

    Attributes:
        kp_orig: Per-joint original stiffness gain, held by STOP_HOLD.
        kd_orig: Per-joint original damping gain, held by STOP_HOLD/RETRACT.
        q_hold: Per-joint hold position (radians) captured at detection.
        tau_grav: Per-joint gravity feed-forward torque (Nm), the model term.
        residual: Per-joint GMO torque residual `r`, direction for RETRACT/ADMITTANCE.
        retract_alpha_rad: RETRACT retreat distance along `r̂`, radians.
        retract_kp_low: RETRACT lowered stiffness, a compliant retreat.
        admittance_gain: ADMITTANCE residual-to-velocity gain `C`.
    """

    kp_orig: tuple[float, ...]
    kd_orig: tuple[float, ...]
    q_hold: tuple[Rad, ...]
    tau_grav: tuple[Nm, ...]
    residual: tuple[float, ...]
    retract_alpha_rad: float = RETRACT_ALPHA_RAD
    retract_kp_low: float = RETRACT_KP_LOW
    admittance_gain: float = ADMITTANCE_GAIN

    def __post_init__(self) -> None:
        """Refuse a context whose per-joint vectors are not all the same width."""
        widths = {
            len(self.kp_orig),
            len(self.kd_orig),
            len(self.q_hold),
            len(self.tau_grav),
            len(self.residual),
        }
        if len(widths) != 1:
            raise ValueError(
                f"reaction context vectors must share one width, got lengths {sorted(widths)}"
            )

    @property
    def width(self) -> int:
        """The per-joint width of this context.

        Returns:
            (int) The number of joints.
        """
        return len(self.q_hold)


@dataclass(frozen=True)
class ReactionCommand:
    """One reaction decision: a continuous-send batch, a decel trajectory, or a directive.

    Exactly one of `batch`/`decel`/`directive` is set, per the strategy's shape. A
    `batch` is re-sent every tick by the latched loop (`FR-SAF-038`/`073`, never a loop
    stop); a `decel` is the category-1 trajectory; a `directive` is the category-0 cut.

    Attributes:
        strategy: The reaction this command realises.
        batch: The MIT frame the loop sends continuously, or None.
        decel: The category-1 decel trajectory, or None.
        directive: The category-0 power-off directive, or None.
        degraded: Whether the frame dropped `τ_grav` for want of `FR-SAF-069` (RETRACT).
        degraded_reason: Why it degraded, empty when it did not.
    """

    strategy: ReactionStrategy
    batch: tuple[ExecutedMitCommand, ...] | None
    decel: DecelTrajectory | None
    directive: PowerOffDirective | None
    degraded: bool
    degraded_reason: str


def _norm(values: tuple[float, ...]) -> float:
    """Return the Euclidean norm of a per-joint vector."""
    return math.sqrt(sum(component * component for component in values))


def _assert_kd_nonzero_where_position_controlled(batch: tuple[ExecutedMitCommand, ...]) -> None:
    """Refuse any command that drives a position with zero damping (`FR-SAF-040`).

    Args:
        batch: The MIT batch to check.

    Raises:
        KdZeroPositionCommandError: If a joint with a live stiffness has `kd == 0`.
    """
    for index, command in enumerate(batch):
        commands_position = command.kp > KP_POSITION_CONTROL_EPSILON
        if commands_position and command.kd == 0.0:
            raise KdZeroPositionCommandError(index)


def _feedforward_torque(
    context: ReactionContext, channel: TorqueChannel
) -> tuple[tuple[Nm, ...], bool]:
    """Return the feed-forward torque to carry, and whether it was degraded to zero.

    When the follower carries the `FR-SAF-069` torque channel the model `τ_grav` rides
    the frame; without it the torque is dropped to zero (the arm sags) and the caller
    records the degradation. This is only reached by strategies that do not *require*
    the channel — the required ones are refused earlier.

    Args:
        context: The reaction context carrying `tau_grav`.
        channel: The follower's feed-forward channel capability.

    Returns:
        (tuple) The per-joint torque and a degraded flag.
    """
    if channel.feedforward_torque:
        return context.tau_grav, False
    return tuple(_ZERO_TORQUE for _ in range(context.width)), True


def _stop_hold_batch(context: ReactionContext) -> tuple[ExecutedMitCommand, ...]:
    """Build STOP_HOLD: hold at `q_hold` with original gains and gravity feed-forward.

    `MIT(kp_orig, kd_orig, q_hold, 0, τ_grav)` (`FR-SAF-038`). The torque channel is
    required (checked before this), so `τ_grav` is always carried.
    """
    return tuple(
        ExecutedMitCommand(kp=kp, kd=kd, q=q, dq=_ZERO_VELOCITY, tau=tau)
        for kp, kd, q, tau in zip(
            context.kp_orig, context.kd_orig, context.q_hold, context.tau_grav, strict=True
        )
    )


def _gravity_comp_batch(context: ReactionContext) -> tuple[ExecutedMitCommand, ...]:
    """Build GRAVITY_COMP: pure gravity feed-forward, compliant (`FR-SAF-039`).

    `MIT(0, 0, 0, 0, τ_grav)`: no stiffness, no damping, no position — the arm floats
    under gravity compensation and a person can push it. Not a position command, so the
    kd≠0 rule does not apply.
    """
    return tuple(
        ExecutedMitCommand(kp=0.0, kd=0.0, q=Rad(0.0), dq=_ZERO_VELOCITY, tau=tau)
        for tau in context.tau_grav
    )


def _retract_batch(
    context: ReactionContext, channel: TorqueChannel
) -> tuple[tuple[ExecutedMitCommand, ...], bool, str]:
    """Build RETRACT: retreat opposite the residual with a lowered stiffness.

    `MIT(kp_low, kd_orig, q_hold − α·r̂, 0, τ_grav)`. Unlike the three required
    reactions, RETRACT does not need the torque channel — without it the retreat still
    happens but `τ_grav` is dropped (the arm sags), which the caller records as a
    degradation rather than a refusal (`12` §2.7.0 "partial").
    """
    torque, degraded = _feedforward_torque(context, channel)
    norm = _norm(context.residual)
    batch: list[ExecutedMitCommand] = []
    for index in range(context.width):
        direction = context.residual[index] / norm if norm > 0.0 else 0.0
        target = Rad(context.q_hold[index].value - context.retract_alpha_rad * direction)
        batch.append(
            ExecutedMitCommand(
                kp=context.retract_kp_low,
                kd=context.kd_orig[index],
                q=target,
                dq=_ZERO_VELOCITY,
                tau=torque[index],
            )
        )
    reason = (
        "RETRACT dropped τ_grav (no FR-SAF-069 torque channel); the arm sags during retreat"
        if degraded
        else ""
    )
    return tuple(batch), degraded, reason


def _admittance_batch(context: ReactionContext) -> tuple[ExecutedMitCommand, ...]:
    """Build ADMITTANCE: yield along the residual as a velocity command (`12` §2.10).

    `MIT(0, kd_orig, ·, dq_cmd = C·r, τ_grav)`: no stiffness, damping kept, a velocity
    proportional to the residual so the arm gives way. Both feed-forward channels are
    required (checked before this). Not a position command (kp=0), so the kd≠0 rule
    does not apply, though `kd_orig` is kept nonzero anyway.
    """
    return tuple(
        ExecutedMitCommand(
            kp=0.0,
            kd=kd,
            q=q,
            dq=RadPerSec(context.admittance_gain * residual),
            tau=tau,
        )
        for kd, q, tau, residual in zip(
            context.kd_orig, context.q_hold, context.tau_grav, context.residual, strict=True
        )
    )


def _decel_trajectory(context: ReactionContext) -> DecelTrajectory:
    """Build STOP_DECEL's category-1 decel frames (reachable on the stock path).

    Position-hold frames at `q_hold` with damping active bring residual motion to rest;
    the frames are position-only (no `τ_grav`), so STOP_DECEL is reachable without
    `FR-SAF-069`. The terminal power-off is authorized separately, only once stopped.
    """
    hold = tuple(
        ExecutedMitCommand(kp=kp, kd=kd, q=q, dq=_ZERO_VELOCITY, tau=_ZERO_TORQUE)
        for kp, kd, q in zip(context.kp_orig, context.kd_orig, context.q_hold, strict=True)
    )
    _assert_kd_nonzero_where_position_controlled(hold)
    return DecelTrajectory(frames=tuple(hold for _ in range(STOP_DECEL_RAMP_STEPS)))


def build_reaction_command(
    strategy: ReactionStrategy,
    context: ReactionContext,
    channel: TorqueChannel,
    confirmation: PowerOffConfirmation | None = None,
) -> ReactionCommand:
    """Build the reaction command for a strategy, enforcing the three safety guards.

    Args:
        strategy: The reaction to build.
        context: The pre-reaction motor state.
        channel: The follower's `FR-SAF-069` feed-forward channel capability.
        confirmation: The POWER_OFF double confirmation; required only for POWER_OFF.

    Returns:
        (ReactionCommand) The reaction, with exactly one of batch/decel/directive set.

    Raises:
        TorqueChannelUnavailableError: If a feed-forward reaction lacks its channel.
        KdZeroPositionCommandError: If a position command would carry `kd == 0`.
        PowerOffConfirmationError: If POWER_OFF lacks the fall warning and confirm.
    """
    require_channels(strategy, channel)

    if strategy is ReactionStrategy.POWER_OFF:
        return _build_power_off(confirmation)
    if strategy is ReactionStrategy.STOP_DECEL:
        return ReactionCommand(
            strategy=strategy,
            batch=None,
            decel=_decel_trajectory(context),
            directive=None,
            degraded=False,
            degraded_reason="",
        )

    batch, degraded, reason = _build_batch(strategy, context, channel)
    if properties(strategy).commands_position:
        _assert_kd_nonzero_where_position_controlled(batch)
    return ReactionCommand(
        strategy=strategy,
        batch=batch,
        decel=None,
        directive=None,
        degraded=degraded,
        degraded_reason=reason,
    )


def _build_batch(
    strategy: ReactionStrategy, context: ReactionContext, channel: TorqueChannel
) -> tuple[tuple[ExecutedMitCommand, ...], bool, str]:
    """Dispatch the continuous-send batch strategies (`FR-SAF-038`/`039`, §2.10)."""
    if strategy is ReactionStrategy.STOP_HOLD:
        return _stop_hold_batch(context), False, ""
    if strategy is ReactionStrategy.GRAVITY_COMP:
        return _gravity_comp_batch(context), False, ""
    if strategy is ReactionStrategy.RETRACT:
        return _retract_batch(context, channel)
    return _admittance_batch(context), False, ""


def _build_power_off(confirmation: PowerOffConfirmation | None) -> ReactionCommand:
    """Build POWER_OFF, refusing it without the fall warning and double confirm."""
    if confirmation is None or not confirmation.is_double_confirmed:
        raise PowerOffConfirmationError(POWER_OFF_FALL_WARNING)
    return ReactionCommand(
        strategy=ReactionStrategy.POWER_OFF,
        batch=None,
        decel=None,
        directive=PowerOffDirective(
            can_opcode=POWER_OFF_CAN_OPCODE, warning=POWER_OFF_FALL_WARNING
        ),
        degraded=False,
        degraded_reason="",
    )


def resume_to_position(
    kp: tuple[float, ...], kd: tuple[float, ...], q: tuple[Rad, ...]
) -> tuple[ExecutedMitCommand, ...]:
    """Build a position command for returning from GRAVITY_COMP, enforcing `FR-SAF-040`.

    Returning to position control from `(kp=0, kd=0)` is the edge the Damiao warning is
    about: sending a position with `kd == 0` here makes the motor vibrate or run away.
    This builder refuses that, so the one dangerous crossing has the kd≠0 rule on it.

    Args:
        kp: Per-joint stiffness to resume with (position control).
        kd: Per-joint damping; refused if zero on any position-controlled joint.
        q: Per-joint target position, radians.

    Returns:
        (tuple[ExecutedMitCommand, ...]) The position command.

    Raises:
        KdZeroPositionCommandError: If a resumed position command carries `kd == 0`.
    """
    batch = tuple(
        ExecutedMitCommand(kp=kp_i, kd=kd_i, q=q_i, dq=_ZERO_VELOCITY, tau=_ZERO_TORQUE)
        for kp_i, kd_i, q_i in zip(kp, kd, q, strict=True)
    )
    _assert_kd_nonzero_where_position_controlled(batch)
    return batch
