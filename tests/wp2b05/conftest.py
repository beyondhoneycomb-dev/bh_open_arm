"""Shared fixtures for the WP-2B-05 no-transmit logging-tap acceptance tests.

The wiring fixture builds the *real* Wave-1 scheduler (`backend.actuation`) with a
`SchedulerLogTap` as its trace and a `FakeCanWriter` as its bus handle, so the tests
exercise pattern A end to end without hardware. The fake writer counts its own sends, so
a test can compare frame count against send count and prove logging rides the tick rather
than driving the bus.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.actuation import (
    ActuationScheduler,
    LeaseManager,
    MailboxProducer,
    ManualClock,
    TargetMailbox,
)
from backend.actuation.can_writer import FakeCanWriter
from backend.friction_log.scheduler_tap import SchedulerLogTap
from backend.friction_log.sink import MemoryLogSink
from contracts.units import Rad

_WIDTH = 16
_LEASE_SEC = 0.05


@dataclass
class Wiring:
    """A wired scheduler and the observables a pattern-A test reads.

    Attributes:
        scheduler: The real scheduler, tapped by `SchedulerLogTap`.
        sink: The memory sink the tap emits into.
        writer: The fake CAN writer, whose `write_count` is the true send count.
        clock: The manual clock driving freshness and timestamps.
        mailbox: The producer-to-scheduler target channel.
        lease: The deadman lease.
    """

    scheduler: ActuationScheduler
    sink: MemoryLogSink
    writer: FakeCanWriter
    clock: ManualClock
    mailbox: TargetMailbox
    lease: LeaseManager


@pytest.fixture
def wiring() -> Wiring:
    """Build a real scheduler tapped by a pattern-A log tap, with a fake CAN writer."""
    clock = ManualClock()
    mailbox = TargetMailbox()
    lease = LeaseManager(_LEASE_SEC)
    producer = MailboxProducer("p", mailbox, clock)
    writer = FakeCanWriter()
    sink = MemoryLogSink()
    scheduler = ActuationScheduler(
        writer,
        mailbox,
        clock,
        lease,
        producer,
        tuple(Rad(0.0) for _ in range(_WIDTH)),
        SchedulerLogTap(sink),
    )
    lease.renew(clock.now())
    return Wiring(scheduler, sink, writer, clock, mailbox, lease)
