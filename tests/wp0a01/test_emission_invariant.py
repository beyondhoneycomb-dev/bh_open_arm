"""Acceptance ① — exactly one emission per tick, under a million injected faults.

Two layers of proof. The decider is shown to be a total order (never zero, never
two) over the whole input grid, which is the structural guarantee. Then the
scheduler is run for a million fault-injected ticks with short freshness and lease
windows so every emission type is exercised, and each tick's one-write invariant is
enforced inside the scheduler — reaching the end with write_count == tick count is
the invariant holding a million times over.
"""

from __future__ import annotations

import itertools

import pytest

from backend.actuation import (
    ActuationScheduler,
    DeciderInput,
    EmissionInvariantError,
    EmissionLabel,
    FaultInjectionHarness,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    TallyTrace,
    TargetMailbox,
    TickTrace,
    decide,
    positions_to_batch,
)
from backend.actuation.can_writer import MIT_BATCH_WIDTH
from backend.actuation.config import LEASE_DURATION_SEC
from backend.actuation.mailbox import TimestampedTarget
from contracts.action import ExecutedMitCommand, RequestedPositionAction
from contracts.units import Deg, Rad

_HOLD_BATCH = positions_to_batch(tuple(Rad(0.0) for _ in range(16)))
_REQUEST = RequestedPositionAction(values=tuple(Deg(1.0) for _ in range(16)))


class _DroppingCanWriter:
    """A writer whose send is a no-op: `write_count` never advances — a dropped frame.

    The realistic failure the in-tick guard must catch: the writer returns without
    faulting, so the arm is never actually commanded, yet nothing raised at the
    send site. Only comparing the writer's own counter across the call reveals it.
    """

    def __init__(self) -> None:
        """Create a writer that silently discards every frame."""
        self._write_count = 0

    @property
    def write_count(self) -> int:
        """Frames actually sent — always zero, because this writer sends none.

        Returns:
            (int) Cumulative successful sends.
        """
        return self._write_count

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Discard the frame without sending it — write_count stays put.

        Args:
            batch: The batch the scheduler asked to send.
        """


class _DoublingCanWriter:
    """A writer that counts two sends for one call — a doubled frame."""

    def __init__(self) -> None:
        """Create a writer that over-counts every send."""
        self._write_count = 0

    @property
    def write_count(self) -> int:
        """Frames actually sent, over-counted by one per call.

        Returns:
            (int) Cumulative (inflated) successful sends.
        """
        return self._write_count

    def mit_control_batch(self, batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Record two sends for a single frame.

        Args:
            batch: The batch the scheduler asked to send.
        """
        self._write_count += 2


def _scheduler_with(writer: object) -> ActuationScheduler:
    """Wire a scheduler around a given CAN writer, otherwise fully valid.

    Args:
        writer: The CAN writer under test.

    Returns:
        (ActuationScheduler) A scheduler whose only anomaly is the writer.
    """
    mailbox = TargetMailbox()
    clock = ManualClock()
    return ActuationScheduler(
        can_writer=writer,  # type: ignore[arg-type]
        mailbox=mailbox,
        clock=clock,
        lease=LeaseManager(LEASE_DURATION_SEC),
        initial_producer=MailboxProducer("p", mailbox, clock),
        initial_hold_positions=tuple(Rad(0.0) for _ in range(MIT_BATCH_WIDTH)),
        trace=TickTrace(),
    )


def test_decider_is_total_over_the_input_grid() -> None:
    """The decider returns exactly one valid emission for every input combination."""
    targets = [None, TimestampedTarget(request=_REQUEST, published_at=0.0)]
    for latched, transition, expired, target, age in itertools.product(
        [False, True], [False, True], [False, True], targets, [0.0, 100.0]
    ):
        state = DeciderInput(
            now=age,
            safety_latched=latched,
            transition_in_progress=transition,
            lease_expired=expired,
            mailbox_target=target,
            hold_batch=_HOLD_BATCH,
            freshness_window_sec=0.05,
            joint_limits=None,
        )
        emission = decide(state)
        assert emission.label in set(EmissionLabel)
        assert len(emission.batch) == 16


def test_million_ticks_never_zero_never_two_emissions() -> None:
    """A million injected faults: every tick emits exactly one, so writes == ticks."""
    ticks = 1_000_000
    harness = FaultInjectionHarness(
        trace=TallyTrace(),
        lease_duration_sec=0.004,
        freshness_window_sec=0.004,
    )
    harness.run_random(ticks, seed=20260721)

    tally = harness.trace
    assert isinstance(tally, TallyTrace)
    # One write per tick: no empty tick (0 emissions) and no double (2+).
    assert harness.can_writer.write_count == ticks
    assert tally.ticks == ticks
    assert sum(tally.label_counts.values()) == ticks
    # Short windows make the fault injection reach every emission type.
    assert tally.labels() == set(EmissionLabel)


def test_dropped_write_trips_the_in_tick_guard() -> None:
    """A writer that no-ops the send leaves write_count still, so the guard fires."""
    scheduler = _scheduler_with(_DroppingCanWriter())
    with pytest.raises(EmissionInvariantError):
        scheduler.tick()


def test_doubled_write_trips_the_in_tick_guard() -> None:
    """A writer that counts two sends for one call is caught the same way."""
    scheduler = _scheduler_with(_DoublingCanWriter())
    with pytest.raises(EmissionInvariantError):
        scheduler.tick()
