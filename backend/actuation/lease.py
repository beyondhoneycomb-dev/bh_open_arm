"""The deadman as a renewal lease (U-4, `04` FR-MAN-050).

The deadman is not a button that is held down; it is a lease that must be renewed
before it expires. Renewal is the operator saying "I am still here"; the absence
of renewal — for any reason, including the operator process dying — expires the
lease, and an expired lease forces a hold on the very tick it expires.

The decisive property (acceptance ④): expiry is decided **only** from the clock and
the last renewal, never from producer or mailbox state. A fresh target sitting in
the mailbox does not keep the arm live if the deadman has lapsed. That
independence is why this is its own object with its own clock read, rather than a
flag folded into the mailbox: folding it in would make expiry depend on whether a
producer happened to publish.
"""

from __future__ import annotations


class LeaseManager:
    """A renewal lease whose expiry is a pure function of clock and last renewal."""

    def __init__(self, duration_sec: float) -> None:
        """Create a lease of the given duration, initially un-renewed.

        A lease that has never been renewed is expired from the start: the arm is
        not live until someone has affirmatively taken the deadman.

        Args:
            duration_sec: How long a renewal keeps the lease live, in seconds.
        """
        self._duration_sec = duration_sec
        self._last_renewed_at: float | None = None

    def renew(self, now: float) -> None:
        """Record a renewal at the given clock time.

        Args:
            now: Current clock reading, in seconds.
        """
        self._last_renewed_at = now

    def is_expired(self, now: float) -> bool:
        """Report whether the lease has lapsed as of `now`.

        Args:
            now: Current clock reading, in seconds.

        Returns:
            (bool) True when never renewed, or when more than the lease duration
            has elapsed since the last renewal.
        """
        if self._last_renewed_at is None:
            return True
        return (now - self._last_renewed_at) > self._duration_sec
