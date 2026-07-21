"""The fault-injection harness — the whole spine on a bench, no hardware.

`02a` §3.1 makes the harness a deliverable, not a test detail: the scheduler is an
`AI-offline` package proved entirely on a fake CAN backend and a controlled clock.
This wires those together with the mailbox, lease, latch, and mode transition, and
exposes the fault levers the acceptance gates pull — go stale, stop renewing the
lease, latch, swap producers — plus a randomized driver that pulls all of them at
once for the million-tick invariant run (acceptance ①).

Determinism is the point. The clock only moves when the harness advances it, and
the randomized driver is seeded, so "the tick the lease expired" and "the tick the
mailbox went stale" are reproducible facts a gate can assert against.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from backend.actuation.can_writer import MIT_BATCH_WIDTH, FakeCanWriter
from backend.actuation.clock import ManualClock
from backend.actuation.config import (
    FRESHNESS_WINDOW_SEC,
    LEASE_DURATION_SEC,
    TICK_INTERVAL_SEC,
)
from backend.actuation.emissions import Emission
from backend.actuation.gateway import JointLimit
from backend.actuation.lease import LeaseManager
from backend.actuation.mailbox import TargetMailbox
from backend.actuation.producer import MailboxProducer
from backend.actuation.scheduler import ActuationScheduler
from backend.actuation.trace import TickTrace, TraceSink
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Rad
from ops.cancel.scheduler import LatchReason

# A neutral 16-dim request and hold pose for bench runs. Zero is not a physical
# claim about the arm; it is a fixed, unit-tagged stand-in so the harness has a
# well-formed target without owning any real joint envelope.
NEUTRAL_REQUEST = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(MIT_BATCH_WIDTH)))
NEUTRAL_HOLD = tuple(Rad(0.0) for _ in range(MIT_BATCH_WIDTH))


def _bench_latch_reason(at: float) -> LatchReason:
    """Build a latch reason for bench-injected latches.

    Args:
        at: Clock reading to stamp the latch with.

    Returns:
        (LatchReason) A well-formed reason attributing the latch to the harness.
    """
    return LatchReason(gate_id="HARNESS", previous_state="PASS", new_state="LATCHED", latched_at=at)


@dataclass
class SwapAccounting:
    """Producer-swap bookkeeping, so leaks are observable (acceptance ②).

    Attributes:
        created: Every producer the harness has stood up, including the first.
        joined: Producers swapped out and joined.
    """

    created: int = 0
    joined: int = 0


class FaultInjectionHarness:
    """The scheduler plus every fault lever, on a fake CAN backend and manual clock."""

    def __init__(
        self,
        trace: TraceSink | None = None,
        tick_interval_sec: float = TICK_INTERVAL_SEC,
        lease_duration_sec: float = LEASE_DURATION_SEC,
        freshness_window_sec: float = FRESHNESS_WINDOW_SEC,
        joint_limits: tuple[JointLimit | None, ...] | None = None,
    ) -> None:
        """Assemble the bench.

        Args:
            trace: Sink for tick records; a fresh `TickTrace` when omitted.
            tick_interval_sec: How far the clock advances per tick.
            lease_duration_sec: Deadman lease duration.
            freshness_window_sec: Age past which a mailbox target is stale.
            joint_limits: Per-joint clamp bounds, or None to clamp no joint.
        """
        self.trace: TraceSink = trace if trace is not None else TickTrace()
        self._tick_interval_sec = tick_interval_sec
        self.clock = ManualClock()
        self.can_writer = FakeCanWriter()
        self.mailbox = TargetMailbox()
        self.lease = LeaseManager(lease_duration_sec)
        self._producer_serial = 0
        self.producer = self._new_producer()
        self.swaps = SwapAccounting(created=1)
        self.scheduler = ActuationScheduler(
            can_writer=self.can_writer,
            mailbox=self.mailbox,
            clock=self.clock,
            lease=self.lease,
            initial_producer=self.producer,
            initial_hold_positions=NEUTRAL_HOLD,
            trace=self.trace,
            joint_limits=joint_limits,
            freshness_window_sec=freshness_window_sec,
        )
        # Live at torque-on: without an initial renewal, the very first tick would
        # read an un-renewed (expired) lease and hold. The bench starts armed.
        self.lease.renew(self.clock.now())

    def _new_producer(self) -> MailboxProducer:
        """Stand up a fresh producer bound to the shared mailbox and clock.

        Returns:
            (MailboxProducer) A new producer with a unique id.
        """
        self._producer_serial += 1
        return MailboxProducer(f"producer-{self._producer_serial}", self.mailbox, self.clock)

    def advance(self) -> None:
        """Move the clock forward by one tick interval."""
        self.clock.advance(self._tick_interval_sec)

    def publish(self, request: RequestedPositionAction = NEUTRAL_REQUEST) -> None:
        """Publish a target from the active producer at the current clock time.

        Args:
            request: The position request to publish.
        """
        self.producer.publish(request)

    def renew(self) -> None:
        """Renew the deadman lease at the current clock time."""
        self.scheduler.renew_lease()

    def latch(self) -> None:
        """Engage the safety latch through the executor's native control.

        Uses `engage_safety_latch`, not the `ops.cancel` `latch_to_hold` contract:
        the bench is inside the actuation domain, and the cancellation contract's
        call site is reserved for `ops/cancel` (`05` §5.2.1).
        """
        self.scheduler.engage_safety_latch(_bench_latch_reason(self.clock.now()))

    def acknowledge(self) -> None:
        """Operator-acknowledge the safety latch."""
        self.scheduler.acknowledge_latch()

    def begin_swap(self) -> None:
        """Prepare a new producer and open an atomic swap to it."""
        incoming = self._new_producer()
        self.swaps.created += 1
        self.scheduler.begin_transition(incoming)
        self.producer = incoming

    def commit_swap(self) -> None:
        """Commit the open swap and join the outgoing producer."""
        outgoing = self.scheduler.commit_transition()
        outgoing.join()
        self.swaps.joined += 1

    def tick(self) -> Emission:
        """Run one scheduler tick.

        Returns:
            (Emission) The emission the tick produced.
        """
        return self.scheduler.tick()

    def run_tick(
        self,
        publish: bool = True,
        renew: bool = True,
        request: RequestedPositionAction = NEUTRAL_REQUEST,
    ) -> Emission:
        """Advance the clock and run one tick, optionally publishing and renewing.

        Args:
            publish: Whether the active producer publishes a fresh target first.
            renew: Whether the deadman lease is renewed first.
            request: The request to publish when `publish` is True.

        Returns:
            (Emission) The emission the tick produced.
        """
        self.advance()
        if renew:
            self.renew()
        if publish:
            self.publish(request)
        return self.tick()

    def run_random(self, ticks: int, seed: int) -> None:
        """Drive the spine through adversarial state combinations (acceptance ①).

        Every lever is toggled pseudo-randomly and independently, and each tick's
        exactly-one-write invariant is enforced inside the scheduler, which raises
        rather than returns on a violation. Reaching the end is the proof.

        Args:
            ticks: Number of ticks to run.
            seed: Seed for reproducibility.
        """
        rng = random.Random(seed)
        for _ in range(ticks):
            self.advance()
            if rng.random() < 0.6:
                self.renew()
            if rng.random() < 0.7:
                self.publish()
            if self.scheduler.in_transition:
                if rng.random() < 0.5:
                    self.commit_swap()
            elif rng.random() < 0.1:
                self.begin_swap()
            if self.scheduler.latch_active:
                if rng.random() < 0.3:
                    self.acknowledge()
            elif rng.random() < 0.02:
                self.latch()
            self.tick()
