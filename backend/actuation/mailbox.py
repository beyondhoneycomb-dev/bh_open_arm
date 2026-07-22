"""The publish-only, latest-wins, single-slot mailbox (`02a` §3.1 ②).

This is the *entire* surface a producer touches. A producer holds a
`TargetMailbox` and nothing else — not the scheduler, not the CAN writer — so the
single-CAN-writer guarantee (`02a` §3.1 ①) is enforced structurally: there is no
attribute path from here to a CAN handle to misuse.

Latest-wins with one slot means a producer that runs faster than the scheduler
never queues; its older targets are simply overwritten, and the scheduler always
reads the freshest. `publish` returns nothing and never blocks — it takes the lock
only to swap one reference — so a producer can never be back-pressured by, or learn
anything about, the consumer.

Threading: `publish` (producer thread) and `take_latest` (scheduler tick) are
guarded by one lock so the slot swap and the read are each atomic with respect to
the other. In the AI-offline fault-injection harness everything runs on one thread
under a controlled clock, but the lock is kept so the type is correct off the test
bench too.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from contracts.action import RequestedPositionAction
from contracts.units import Nm


@dataclass(frozen=True)
class TimestampedTarget:
    """A producer's position request, stamped with when it was published.

    The payload is a CTR-ACT `RequestedPositionAction` (the pre-clamp, position-
    only request); the scheduler clamps it to an accepted target before emitting.
    The timestamp is read from the same clock the scheduler ticks against, so
    freshness is a comparison on one time base, never a wall-clock guess.

    Attributes:
        request: The 16-dim bimanual position request, in degrees (CTR-ACT).
        published_at: Clock reading taken when the producer published, in seconds.
        feedforward_torque: Optional per-joint feed-forward torque routed into the
            emitted MIT frame (`12` §2.7.0: the send_action tau=0 hardcode released
            by the gateway, `WP-1-03`). None — the default — is a position-only
            command, zero feed-forward torque; a hold is always position-only.
    """

    request: RequestedPositionAction
    published_at: float
    feedforward_torque: tuple[Nm, ...] | None = None


class TargetMailbox:
    """A one-slot, latest-wins, non-blocking channel from a producer to the scheduler.

    Ownership: the producer side calls only `publish`. `take_latest` is the
    scheduler's read and is not part of the producer contract — a producer never
    receives an object on which calling it would matter, because it only ever holds
    this mailbox to publish into.
    """

    def __init__(self) -> None:
        """Create an empty mailbox."""
        self._lock = threading.Lock()
        self._slot: TimestampedTarget | None = None

    def publish(self, target: TimestampedTarget) -> None:
        """Overwrite the slot with the latest target. Non-blocking, returns nothing.

        Args:
            target: The timestamped position request to make current.
        """
        with self._lock:
            self._slot = target

    def take_latest(self) -> TimestampedTarget | None:
        """Read the current target without consuming it (scheduler side).

        The slot is not cleared on read: a hold that keeps re-reading the same
        target is the correct behaviour when a producer has simply stopped
        publishing but has not gone stale. Staleness is decided by the timestamp,
        not by whether anyone read the slot.

        Returns:
            (TimestampedTarget | None) The freshest published target, or None when
            nothing has ever been published.
        """
        with self._lock:
            return self._slot
