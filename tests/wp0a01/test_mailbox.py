"""Interface contract ② — the mailbox is publish-only, latest-wins, single-slot.

`publish` returns nothing and overwrites the one slot, so a producer that outruns
the scheduler never queues and never blocks — its stale targets are simply
replaced, and the scheduler reads the freshest. Reading does not consume: a slot
re-read while a producer pauses stays available, and staleness (not consumption)
decides whether it is still honoured.
"""

from __future__ import annotations

from backend.actuation import TargetMailbox, TimestampedTarget
from contracts.action import RequestedPositionAction
from contracts.units import Deg


def _target(value: float, at: float) -> TimestampedTarget:
    """Build a uniform 16-dim target at a value and time."""
    request = RequestedPositionAction(values=tuple(Deg(value) for _ in range(16)))
    return TimestampedTarget(request=request, published_at=at)


def test_publish_returns_none() -> None:
    """Publish is fire-and-forget: it hands nothing back."""
    mailbox = TargetMailbox()
    assert mailbox.publish(_target(1.0, 0.0)) is None


def test_latest_wins_single_slot() -> None:
    """Successive publishes leave only the most recent target."""
    mailbox = TargetMailbox()
    mailbox.publish(_target(1.0, 0.0))
    mailbox.publish(_target(2.0, 1.0))
    mailbox.publish(_target(3.0, 2.0))
    latest = mailbox.take_latest()
    assert latest is not None
    assert latest.published_at == 2.0
    assert latest.request.values[0] == Deg(3.0)


def test_empty_mailbox_reads_none() -> None:
    """A mailbox that was never published to reads as empty."""
    assert TargetMailbox().take_latest() is None


def test_read_does_not_consume() -> None:
    """Re-reading returns the same target: reading is not consuming."""
    mailbox = TargetMailbox()
    mailbox.publish(_target(5.0, 0.0))
    first = mailbox.take_latest()
    second = mailbox.take_latest()
    assert first is second
