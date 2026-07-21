"""The clock the scheduler reads, and the controlled one the harness drives.

Every time-dependent decision in the spine — mailbox freshness, lease expiry, the
no-send interval — reads `Clock.now()` rather than the wall clock. That is what
makes fault injection deterministic: the harness advances a `ManualClock` by an
exact amount per tick, so "the tick on which the lease expires" is a reproducible
fact, not a race against real time.
"""

from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    """A monotonic source of seconds the scheduler reads once per tick."""

    def now(self) -> float:
        """Return the current time in seconds.

        Returns:
            (float) Monotonic seconds on this clock's own time base.
        """
        ...


class ManualClock:
    """A clock advanced explicitly, for deterministic fault injection.

    Time moves only when `advance` is called, so a test controls exactly how much
    simulated time passes between ticks and can place an expiry on a chosen tick.
    """

    def __init__(self, start: float = 0.0) -> None:
        """Create a clock reading `start` seconds.

        Args:
            start: Initial time in seconds.
        """
        self._now = start

    def now(self) -> float:
        """Return the current simulated time.

        Returns:
            (float) Seconds since this clock's start.
        """
        return self._now

    def advance(self, seconds: float) -> None:
        """Move simulated time forward.

        Args:
            seconds: Amount to advance, in seconds; must be non-negative so the
                clock stays monotonic.

        Raises:
            ValueError: If `seconds` is negative.
        """
        if seconds < 0.0:
            raise ValueError(f"clock cannot move backwards: {seconds}")
        self._now += seconds
