"""The spine invariant for WP-4A-07: the engine PUBLISHES; the committed scheduler WRITES.

SPINE §2-1: the inference producer publishes a timestamped target to the mailbox, and
the committed `ActuationScheduler` is the sole CAN writer. These tests wire the real
scheduler (via its fault-injection harness) to the mailbox the session publishes into,
then show a sync tick drives exactly one scheduler CAN write — and that the adapter tree
contains no reference to the CAN handle at all (the committed `staticcheck`, run over our
own source). The engine imports the scheduler; it does not reimplement it, and it never
writes CAN.
"""

from __future__ import annotations

from pathlib import Path

from backend.actuation import (
    EmissionLabel,
    FaultInjectionHarness,
    find_producer_can_access,
)
from backend.inference.adapter import ActParams, InferenceBackend, InferenceSession
from tests.wp4a07.support import FixturePolicy, make_dummy_robot

ADAPTER_ROOT = Path("backend/inference/adapter")


def test_sync_tick_publishes_a_target_the_scheduler_accepts() -> None:
    """A sync tick publishes to the mailbox; the committed scheduler accepts and writes once."""
    harness = FaultInjectionHarness()
    session = InferenceSession(
        robot=make_dummy_robot(),
        mailbox=harness.mailbox,
        clock=harness.clock,
        policy=FixturePolicy(),
        fps=30.0,
    )
    session.switch_backend(InferenceBackend.SYNC, ActParams())

    harness.advance()
    harness.renew()
    request = session.sync_tick()

    latest = harness.mailbox.take_latest()
    assert latest is not None
    assert latest.request == request

    writes_before = harness.can_writer.write_count
    emission = harness.tick()
    assert emission.label is EmissionLabel.ACCEPTED_TARGET
    assert harness.can_writer.write_count == writes_before + 1


def test_scheduler_is_the_only_writer_across_many_ticks() -> None:
    """Over many published targets, every CAN write is the scheduler's, one per tick."""
    harness = FaultInjectionHarness()
    session = InferenceSession(
        robot=make_dummy_robot(),
        mailbox=harness.mailbox,
        clock=harness.clock,
        policy=FixturePolicy(),
        fps=30.0,
    )
    session.switch_backend(InferenceBackend.SYNC, ActParams())

    ticks = 50
    for _ in range(ticks):
        harness.advance()
        harness.renew()
        session.sync_tick()
        harness.tick()
    assert harness.can_writer.write_count == ticks


def test_adapter_tree_never_reaches_the_can_handle() -> None:
    """The committed producer-CAN-access scan finds nothing in the adapter source.

    Structural proof the inference engine is a pure publisher: no import of the CAN
    writer module and no reference to its write symbols anywhere under the adapter tree.
    """
    assert find_producer_can_access(ADAPTER_ROOT) == []
