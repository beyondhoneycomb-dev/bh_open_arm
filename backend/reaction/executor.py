"""The reaction executor — engages the reused Wave-1 latch and proves continuous send.

This is the seam between a confirmed collision and the arm's behaviour. It does two
things and holds no CAN handle of its own:

- **Latch through the Wave-1 scheduler, never a second latch.** A confirmed collision
  engages the scheduler's one-way `SafetyLatch` (`backend.actuation`) — the same latch
  a deadman release or a cancellation uses — so there is one latch, held until an
  operator ack (`FR-SAF-043`). `auto_resume=false` is inherent: clearing the latch is
  the operator's `acknowledge`, and nothing here re-arms motion on its own.
- **Prove the stop is not a loop stop.** `pump` runs scheduler ticks while latched; the
  scheduler emits `SAFETY_LATCH_HOLD` every tick and writes exactly one CAN frame, so
  the frame stream never stops (`FR-SAF-038`/`073`, `NFR-SAF-007`). A tick that emitted
  zero frames raises inside the scheduler, so reaching the pumped count *is* the proof
  the command stream kept flowing — an interruption would be a raised error, not a
  silent pass (the negative branch: stream interruption is `FAIL_BLOCKING`).

The reaction *frame* (STOP_HOLD's `MIT(kp_orig, kd_orig, q_hold, 0, τ_grav)`) is built
by `frame`; `stream_reaction_frames` re-sends that exact frame through a reused
`CanWriter` so the continuous send of the τ_grav-bearing frame is observable on the
fake writer (the offline candump), distinct from the scheduler's generic hold.
"""

from __future__ import annotations

from typing import Protocol

from backend.actuation import CanWriter, Emission
from backend.reaction.capability import TorqueChannel
from backend.reaction.frame import (
    PowerOffConfirmation,
    ReactionCommand,
    ReactionContext,
    build_reaction_command,
)
from backend.reaction.policy import ReactionPolicy
from ops.cancel.scheduler import LatchReason


class SchedulerLike(Protocol):
    """The slice of `ActuationScheduler` the executor drives (the reused single writer).

    `ActuationScheduler` satisfies this structurally; a test double may too. The
    executor never reaches past this surface for a CAN handle — the scheduler is the
    single writer (`02a` §3.1 ①), and the reaction only latches it and reads its ticks.
    """

    @property
    def latch_active(self) -> bool:
        """Whether the safety latch is currently held."""
        ...

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the one-way safety latch with a cause."""
        ...

    def acknowledge_latch(self) -> None:
        """Clear the safety latch — the sole operator-driven release."""
        ...

    def tick(self) -> Emission:
        """Run one scheduler tick, writing exactly one CAN frame."""
        ...


class ReactionExecutor:
    """Turns a confirmed collision into a latched reaction on the reused scheduler.

    Ownership: holds the scheduler (not owned — the runtime owns it), the reaction
    policy, and the follower's feed-forward channel capability. Holds no CAN handle;
    the scheduler is the single writer. The last-built reaction command is retained for
    the caller to install/inspect, not executed here.
    """

    def __init__(
        self,
        scheduler: SchedulerLike,
        policy: ReactionPolicy,
        channel: TorqueChannel,
    ) -> None:
        """Wire the executor to the scheduler, policy, and channel capability.

        Args:
            scheduler: The reused actuation scheduler holding the one-way latch.
            policy: The reaction strategy and its (frozen) latch behaviour.
            channel: The follower's `FR-SAF-069` feed-forward channel capability.
        """
        self._scheduler = scheduler
        self._policy = policy
        self._channel = channel
        self._command: ReactionCommand | None = None

    @property
    def is_latched(self) -> bool:
        """Whether the reaction latch is currently held (until an operator ack)."""
        return self._scheduler.latch_active

    @property
    def reaction_command(self) -> ReactionCommand | None:
        """The most recent reaction command built, or None before the first response."""
        return self._command

    def respond(
        self,
        context: ReactionContext,
        now: float,
        confirmation: PowerOffConfirmation | None = None,
    ) -> ReactionCommand:
        """Build the policy's reaction and latch the scheduler (`FR-SAF-043`).

        The latch is engaged for every strategy — a collision reaction latches
        regardless of which mode it is, and only an operator ack clears it. The reaction
        command is built first, so a refused build (missing channel, kd=0, unconfirmed
        power-off) raises before the latch is touched.

        Args:
            context: The pre-reaction motor state.
            now: The clock reading to stamp the latch with.
            confirmation: The POWER_OFF double confirmation, when the policy is POWER_OFF.

        Returns:
            (ReactionCommand) The reaction the policy produced.
        """
        command = build_reaction_command(
            self._policy.strategy, context, self._channel, confirmation
        )
        self._scheduler.engage_safety_latch(
            _reaction_latch_reason(self._policy.strategy.value, now)
        )
        self._command = command
        return command

    def acknowledge(self) -> None:
        """Operator-acknowledge the reaction latch — the only path that clears it."""
        self._scheduler.acknowledge_latch()

    def pump(self, cycles: int) -> list[Emission]:
        """Run scheduler ticks while latched, proving the frame stream never stops.

        Each tick writes exactly one CAN frame or the scheduler raises, so returning a
        full list of `cycles` emissions is the proof the command stream kept flowing
        under the latch (`FR-SAF-038`/`073`).

        Args:
            cycles: Number of scheduler ticks to run.

        Returns:
            (list[Emission]) The emission of each tick, in order.
        """
        return [self._scheduler.tick() for _ in range(cycles)]


def _reaction_latch_reason(strategy_name: str, now: float) -> LatchReason:
    """Build the `LatchReason` a collision reaction engages the latch with.

    Args:
        strategy_name: The reaction strategy value, recorded as the latch cause.
        now: Clock reading to stamp the latch with.

    Returns:
        (LatchReason) A reason attributing the latch to the collision reaction.
    """
    return LatchReason(
        gate_id=f"COLLISION_REACTION:{strategy_name}",
        previous_state="DETECTED",
        new_state="LATCHED",
        latched_at=now,
    )


def stream_reaction_frames(writer: CanWriter, command: ReactionCommand, cycles: int) -> int:
    """Re-send a reaction's continuous batch through a writer, returning frames sent.

    The offline candump: writing the same τ_grav-bearing STOP_HOLD frame every cycle
    demonstrates the "continuous send, never a loop stop" contract on the reused fake
    writer, and that the frame count equals the cycle count (no interruption). Only the
    continuous-send strategies carry a batch; a decel or a power-off has none.

    Args:
        writer: The reused CAN writer (a `FakeCanWriter` in the offline harness).
        command: A reaction command whose `batch` is the frame to re-send.
        cycles: Number of times to send the frame.

    Returns:
        (int) The number of frames actually sent.

    Raises:
        ValueError: If the command carries no continuous-send batch.
    """
    if command.batch is None:
        raise ValueError(
            f"{command.strategy.value} has no continuous-send batch to stream; only STOP_HOLD, "
            f"GRAVITY_COMP, RETRACT and ADMITTANCE re-send a frame"
        )
    before = writer.write_count
    for _ in range(cycles):
        writer.mit_control_batch(command.batch)
    return writer.write_count - before
