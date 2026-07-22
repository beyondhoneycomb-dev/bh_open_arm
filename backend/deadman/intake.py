"""A bounded, class-priority intake so renewals are never delayed behind bulk frames.

Acceptance ⑧ requires the lease renewal stream not to be held up by the camera-frame
stream (`02b` §1.0: the lease "must be the highest-priority class queue"). The real
head-of-line mitigation lives in the WS transport frozen as `CTR-WS@v1` (`WP-3A-04`);
Wave 2A has no WS yet, so this is the deadman-side intake that models the invariant
the transport must preserve — a class-separated bounded queue where the renewal
class is always drained ahead of the bulk (camera) class and is never dropped under
bulk pressure. It is the reuse seam the WS queue will sit on top of, not a second
copy of it.

This is not the Wave-1 target mailbox. That mailbox is a single-slot, latest-wins
channel for position *targets*, where overwriting an old target with a newer one is
correct. Renewals are the opposite: each carries a distinct sequence for anti-replay,
so the renewal class preserves order and drops nothing, while only the bulk class is
allowed to shed its oldest under pressure.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Generic, TypeVar

_T = TypeVar("_T")


class IntakeClass(Enum):
    """The two priority classes sharing the intake, highest first.

    RENEWAL outranks BULK unconditionally: a full bulk backlog can never delay or
    displace a renewal, which is the head-of-line guarantee the deadman needs.
    """

    RENEWAL = "renewal"
    BULK = "bulk"


class RenewalIntake(Generic[_T]):
    """A two-class bounded queue that drains all renewals before any bulk item.

    Ownership: the producer side calls `offer`; the consumer (the deadman driver)
    calls `drain`. Both classes are bounded so memory is capped, but only the bulk
    class sheds under pressure — a renewal is never dropped to make room for a
    camera frame, and never waits behind one.
    """

    def __init__(self, renewal_capacity: int, bulk_capacity: int) -> None:
        """Create an intake with a bound per class.

        Args:
            renewal_capacity: Maximum buffered renewals. Sized to the renewal cadence
                so it is not reached in normal operation; reaching it is itself a
                fault the caller should surface, so an overflowing renewal is
                reported, not silently dropped.
            bulk_capacity: Maximum buffered bulk (camera) items. The oldest is shed
                when a new one arrives full, because a stale frame has no value.
        """
        self._renewals: deque[_T] = deque(maxlen=renewal_capacity)
        self._bulk: deque[_T] = deque(maxlen=bulk_capacity)
        self._renewal_capacity = renewal_capacity
        self._bulk_dropped = 0
        self._renewal_overflowed = 0

    @property
    def bulk_dropped(self) -> int:
        """Count of bulk items shed under pressure since construction.

        Returns:
            (int) Cumulative bulk drops.
        """
        return self._bulk_dropped

    @property
    def renewal_overflowed(self) -> int:
        """Count of renewals refused because the renewal class was full.

        A non-zero value is a fault: the renewal class is sized never to fill in
        normal operation, so filling it means renewals are arriving faster than they
        drain, which the caller must treat as a link fault rather than ignore.

        Returns:
            (int) Cumulative renewal overflows.
        """
        return self._renewal_overflowed

    def offer(self, item: _T, intake_class: IntakeClass) -> bool:
        """Enqueue an item into its class. Non-blocking.

        Args:
            item: The item to enqueue.
            intake_class: Which priority class it belongs to.

        Returns:
            (bool) True if the item was buffered. A renewal returns False (and is
            counted as an overflow) only when the renewal class is already full — it
            is never dropped to admit a bulk item. A bulk item is always accepted,
            shedding the oldest bulk item when full.
        """
        if intake_class is IntakeClass.RENEWAL:
            if len(self._renewals) >= self._renewal_capacity:
                self._renewal_overflowed += 1
                return False
            self._renewals.append(item)
            return True
        if len(self._bulk) == self._bulk.maxlen:
            # deque drops the oldest on append at maxlen; count it as a bulk drop.
            self._bulk_dropped += 1
        self._bulk.append(item)
        return True

    def drain(self) -> list[_T]:
        """Remove and return everything buffered, renewals first, then bulk.

        Returns:
            (list) All buffered items with every renewal ahead of every bulk item,
            each class in arrival order. The intake is empty afterwards.
        """
        ordered = list(self._renewals) + list(self._bulk)
        self._renewals.clear()
        self._bulk.clear()
        return ordered
