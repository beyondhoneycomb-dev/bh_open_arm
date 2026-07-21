"""The ActuationScheduler — the runtime spine and the single CAN writer.

Everything the rest of the plan does to the arm passes through one loop here.
Between torque-on and torque-off, CAN writes happen **only** in `tick`
(`02a` §3.1 ①): the scheduler holds the sole `CanWriter`, producers hold only a
mailbox, and `tick` performs exactly one MIT batch write. That single write per
tick is the runtime form of the "exactly one of four emissions" invariant — the
decider yields one `Emission`, `tick` turns it into one send, and it asserts the
count is one, so a tick that emitted zero (a dropped arm) or two (a contested
command) fails loudly rather than silently (acceptance ①).

Relationship to `ops/cancel` (`WP-BOOT-04`): that package owns the *call contract*
`latch_to_hold` and builds only a minimal `ActuationScheduler` Protocol to test
cancellation ordering; it explicitly delegates the *physical executor* to this WP.
This class is that executor. It implements `latch_to_hold(reason)` with the
`ops.cancel` `LatchReason`, so a real scheduler satisfies the BOOT-04 Protocol and
can be handed straight to `ops.cancel.executor.cancel_stage` — the two are unified
at the interface without either reimplementing the other, and the BOOT-04 tests
(which use their own Protocol double) are untouched.
"""

from __future__ import annotations

from backend.actuation.can_writer import MIT_BATCH_WIDTH, CanWriter
from backend.actuation.clock import Clock
from backend.actuation.config import FRESHNESS_WINDOW_SEC
from backend.actuation.decider import DeciderInput, decide
from backend.actuation.emissions import Emission, EmissionLabel
from backend.actuation.gateway import JointLimit, positions_to_batch
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.actuation.mailbox import TargetMailbox
from backend.actuation.producer import Producer
from backend.actuation.trace import TickRecord, TraceSink
from backend.actuation.transition import ModeTransition
from contracts.units import Rad
from ops.cancel.scheduler import LatchReason

_VALID_LABELS = frozenset(EmissionLabel)


class EmissionInvariantError(RuntimeError):
    """Raised when a tick did not resolve to exactly one CAN write.

    This is the "zero emissions is a violation" guard (`02a` §3.1 ③) in its
    unstrippable form: a real raise, not an `assert`, because the invariant it
    guards is the difference between a held arm and a dropped one.
    """


class ActuationScheduler:
    """The one loop that writes CAN, from torque-on to torque-off.

    Ownership: holds the sole `CanWriter`. Producers never receive it; they publish
    to the mailbox. The lease, latch, and mode transition are read each tick to
    decide the emission, and none of them can bypass the single write path.
    """

    def __init__(
        self,
        can_writer: CanWriter,
        mailbox: TargetMailbox,
        clock: Clock,
        lease: LeaseManager,
        initial_producer: Producer,
        initial_hold_positions: tuple[Rad, ...],
        trace: TraceSink,
        joint_limits: tuple[JointLimit | None, ...] | None = None,
        freshness_window_sec: float = FRESHNESS_WINDOW_SEC,
    ) -> None:
        """Wire the spine at torque-on.

        Args:
            can_writer: The sole CAN handle; stored privately and never exposed.
            mailbox: The producer-to-scheduler target channel.
            clock: Time source for freshness, lease, and send timestamps.
            lease: The deadman renewal lease.
            initial_producer: The producer live at torque-on.
            initial_hold_positions: Joint positions to hold at before any accepted
                target, in radians, width `MIT_BATCH_WIDTH`.
            trace: Sink for per-tick audit records.
            joint_limits: Per-joint clamp bounds, or None to clamp no joint.
            freshness_window_sec: Age past which a mailbox target is stale.

        Raises:
            ValueError: If `initial_hold_positions` is not `MIT_BATCH_WIDTH` wide.
        """
        if len(initial_hold_positions) != MIT_BATCH_WIDTH:
            raise ValueError(
                f"initial hold positions must be {MIT_BATCH_WIDTH} wide, "
                f"got {len(initial_hold_positions)}"
            )
        self._can_writer = can_writer
        self._mailbox = mailbox
        self._clock = clock
        self._lease = lease
        self._transition = ModeTransition(initial_producer)
        self._latch = SafetyLatch()
        # The hold frame is cached and re-sent: a hold is the same MIT position-hold
        # frame (`02a` §3.1 ⑤), rebuilt only when an accepted target moves the hold
        # point. This is what keeps a held tick allocation-free.
        self._hold_batch = positions_to_batch(initial_hold_positions)
        self._trace = trace
        self._joint_limits = joint_limits
        self._freshness_window_sec = freshness_window_sec
        self._tick_index = 0

    @property
    def tick_index(self) -> int:
        """Number of ticks executed since torque-on.

        Returns:
            (int) Monotonic tick count.
        """
        return self._tick_index

    @property
    def active_producer_id(self) -> str:
        """Identity of the currently active producer.

        Returns:
            (str) The active producer's id.
        """
        return self._transition.active_id

    @property
    def latch_active(self) -> bool:
        """Whether the safety latch is currently held.

        Returns:
            (bool) True until an operator ack after a latch.
        """
        return self._latch.is_active

    @property
    def freshness_window_sec(self) -> float:
        """Age past which a mailbox target is considered stale.

        Returns:
            (float) The freshness window, in seconds.
        """
        return self._freshness_window_sec

    @property
    def in_transition(self) -> bool:
        """Whether a producer swap is currently bracketed.

        Returns:
            (bool) True between `begin_transition` and `commit_transition`.
        """
        return self._transition.in_progress

    def renew_lease(self) -> None:
        """Renew the deadman lease at the current clock time (an operator hold)."""
        self._lease.renew(self._clock.now())

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the safety latch — the executor's native latch control.

        This is what a safety monitor, a deadman release path, or the fault harness
        calls to put the arm into a latched hold. After it, every tick emits
        SAFETY_LATCH_HOLD until `acknowledge_latch`.

        It is deliberately distinct from `latch_to_hold`: that method is the narrow
        cancellation contract `ops/cancel` owns and is the only latch symbol its
        locality check polices, whereas this is the general safety-engage the
        executor exposes to callers inside its own domain.

        Args:
            reason: Cause and timestamp of the latch.
        """
        self._latch.engage(reason)

    def latch_to_hold(self, reason: LatchReason) -> None:
        """Engage the safety latch through the `ops.cancel` cancellation contract.

        This is the method `ops.cancel.executor.cancel_stage` calls on a
        latch-to-hold stage; `05` §5.2.1 keeps the *call* to it inside `ops/cancel`,
        which is why the executor's own callers use `engage_safety_latch` instead.
        It delegates to the same single latch, so a cancellation and a native safety
        engage cannot diverge.

        Args:
            reason: Cause and timestamp of the latch.
        """
        self.engage_safety_latch(reason)

    def acknowledge_latch(self) -> None:
        """Clear the safety latch — the sole legitimate release, an operator ack."""
        self._latch.acknowledge()

    def begin_transition(self, incoming: Producer) -> None:
        """Open an atomic producer swap; ticks hold until it is committed.

        Args:
            incoming: The already-prepared new producer.
        """
        self._transition.begin(incoming)

    def commit_transition(self) -> Producer:
        """Commit the swap and return the outgoing producer to join.

        Returns:
            (Producer) The producer swapped out, for the caller to join.
        """
        return self._transition.commit()

    def tick(self) -> Emission:
        """Run one scheduler tick: decide, write exactly one frame, record.

        Returns:
            (Emission) The single emission this tick produced.

        Raises:
            EmissionInvariantError: If the tick did not resolve to exactly one CAN
                write — the dropped-arm / contested-command guard.
        """
        now = self._clock.now()
        state = DeciderInput(
            now=now,
            safety_latched=self._latch.is_active,
            transition_in_progress=self._transition.in_progress,
            lease_expired=self._lease.is_expired(now),
            mailbox_target=self._mailbox.take_latest(),
            hold_batch=self._hold_batch,
            freshness_window_sec=self._freshness_window_sec,
            joint_limits=self._joint_limits,
        )
        emission = decide(state)
        if emission.label not in _VALID_LABELS:
            raise EmissionInvariantError(f"decider returned an unknown label: {emission.label}")

        # Snapshot the writer's *own* successful-send counter across the call. A
        # mirror field the scheduler increments itself could only ever read back
        # the increment it just made; reading the writer's counter is what turns
        # this into a real check — a writer that drops the frame leaves the count
        # unchanged, one that doubles it advances by two, and both fail here.
        writes_before = self._can_writer.write_count
        self._can_writer.mit_control_batch(emission.batch)
        if self._can_writer.write_count - writes_before != 1:
            raise EmissionInvariantError("a tick must perform exactly one CAN write")

        # An accepted target advances the frame the next hold will re-send, so a
        # hold always parks the arm where it was last legitimately commanded rather
        # than at torque-on. The accepted command is itself a valid hold frame
        # (position-only, zero feed-forward), so it becomes the cached hold batch.
        if emission.label is EmissionLabel.ACCEPTED_TARGET:
            self._hold_batch = emission.batch

        self._trace.record(
            TickRecord(
                index=self._tick_index,
                at=now,
                label=emission.label,
                reason=emission.reason,
                batch=emission.batch,
            )
        )
        self._tick_index += 1
        return emission
