"""What a producer is, from the scheduler's side of the wall.

A producer is any source of targets — teleop, replay, a policy, manual jog. The
scheduler knows almost nothing about it: an identity (for the trace) and a way to
join it once it has been swapped out. A producer *publishes* to a `TargetMailbox`
and never receives the scheduler or a CAN handle, which is the structural half of
the single-CAN-writer invariant (`02a` §3.1 ①).

`MailboxProducer` is the reference shape: it holds a mailbox and a clock and does
exactly one privileged thing — publish. It is what a real producer's target path
compiles down to, and it is the clean counter-fixture to the "producer reaches for
the CAN handle" violation acceptance ⑥ rejects.
"""

from __future__ import annotations

from typing import Protocol

from backend.actuation.clock import Clock
from backend.actuation.mailbox import TargetMailbox, TimestampedTarget
from contracts.action import RequestedPositionAction


class Producer(Protocol):
    """A swappable source of targets, as the scheduler sees it."""

    @property
    def producer_id(self) -> str:
        """Stable identity used in traces and swap accounting.

        Returns:
            (str) This producer's id.
        """
        ...

    def join(self) -> None:
        """Stop this producer and release its resources after it is swapped out."""
        ...


class MailboxProducer:
    """A producer whose only privilege is publishing to its mailbox.

    It cannot see the scheduler or the CAN writer; it holds a mailbox and a clock.
    That is the whole point — the type has no member through which a CAN frame
    could be sent, so the single-writer rule is not a convention it must remember
    but a shape it cannot violate.
    """

    def __init__(self, producer_id: str, mailbox: TargetMailbox, clock: Clock) -> None:
        """Bind a producer to the mailbox it publishes into.

        Args:
            producer_id: Stable identity for traces and swap accounting.
            mailbox: The one-slot channel to the scheduler.
            clock: The shared clock, so published timestamps share the scheduler's
                time base.
        """
        self._producer_id = producer_id
        self._mailbox = mailbox
        self._clock = clock
        self._joined = False

    @property
    def producer_id(self) -> str:
        """Stable identity used in traces and swap accounting.

        Returns:
            (str) This producer's id.
        """
        return self._producer_id

    @property
    def joined(self) -> bool:
        """Whether this producer has been joined (swapped out and released).

        Returns:
            (bool) True after `join`.
        """
        return self._joined

    def publish(self, request: RequestedPositionAction) -> None:
        """Publish a position request stamped with the current clock time.

        Args:
            request: The 16-dim bimanual position request, in degrees.
        """
        self._mailbox.publish(TimestampedTarget(request=request, published_at=self._clock.now()))

    def join(self) -> None:
        """Release the producer. Idempotent; a double join is not an error."""
        self._joined = True
