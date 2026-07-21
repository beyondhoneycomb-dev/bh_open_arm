"""A well-formed producer: it publishes to a mailbox and touches nothing else.

The clean counter-fixture to acceptance ⑥. Scanning it must yield no CAN-handle
finding — proving the scan does not over-flag a legitimate producer, which holds
only the mailbox and never reaches for the bus.
"""

from __future__ import annotations

from backend.actuation.mailbox import TargetMailbox, TimestampedTarget
from contracts.action import RequestedPositionAction
from contracts.units import Deg


def publish_neutral(mailbox: TargetMailbox, now: float) -> None:
    """Publish a neutral position request; the mailbox is the only handle held.

    Args:
        mailbox: The publish-only channel to the scheduler.
        now: Clock reading to stamp the target with.
    """
    request = RequestedPositionAction(values=tuple(Deg(0.0) for _ in range(16)))
    mailbox.publish(TimestampedTarget(request=request, published_at=now))
