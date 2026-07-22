"""The client-clock offset estimator and the age filter — the *only* client-clock code.

This module exists to quarantine every use of `issued_mono_client` in one place.
The expiry decision (`DeadmanMonitor`, `LeaseManager.is_expired`) must reference
zero client-supplied time (acceptance ⑥); isolating the client clock here makes
that a property a static check can verify by looking at which module a symbol lives
in, rather than by reasoning about every call site.

The offset aligns the client and server monotonic clocks once, at the moment a
generation is first renewed. After that, a renewal's age is how much later the
server received it than the client stamped it, both mapped to a common frame. A
renewal issued in order but delayed in transit therefore shows a large age and is
discarded — which is the whole point: on the deadman, a delayed renewal is invalid,
not merely late.
"""

from __future__ import annotations


class ClientClockOffset:
    """A once-per-generation estimate of (server clock − client clock), for age only.

    Lifecycle: estimated from the first accepted renewal of a generation, and reset
    on re-arm so a new generation re-estimates. It is never used to decide expiry —
    only to compute the transit age of a renewal, which the receiver compares to
    `max_lease_age`. The client clock reaches no further than this object.
    """

    def __init__(self) -> None:
        """Create an un-estimated offset (no generation renewed yet)."""
        self._offset_sec: float | None = None

    @property
    def is_estimated(self) -> bool:
        """Whether an offset has been established for the current generation.

        Returns:
            (bool) True once the first renewal of a generation has set the baseline.
        """
        return self._offset_sec is not None

    def estimate(self, issued_mono_client: float, server_received_at: float) -> None:
        """Set the baseline from a generation's first renewal.

        The first renewal defines the alignment, so its own age is zero by
        construction — it cannot be discarded for age. Subsequent renewals are
        measured against it.

        Args:
            issued_mono_client: The client's issue time of the first renewal, in
                seconds on the client clock.
            server_received_at: The server clock reading when it was received, in
                seconds on the server clock.
        """
        self._offset_sec = server_received_at - issued_mono_client

    def reset(self) -> None:
        """Forget the baseline so the next generation re-estimates it (re-arm)."""
        self._offset_sec = None

    def age(self, issued_mono_client: float, server_received_at: float) -> float:
        """Return a renewal's transit age in seconds, mapped into the server frame.

        Args:
            issued_mono_client: The renewal's client issue time, in seconds.
            server_received_at: The server clock reading at receipt, in seconds.

        Returns:
            (float) `server_received_at − (issued_mono_client + offset)`: how much
            later the server saw the renewal than the client stamped it.

        Raises:
            ValueError: If called before the offset is estimated — an age has no
                meaning without a baseline, and returning a plausible number would
                let an unmeasured message slip past the filter.
        """
        if self._offset_sec is None:
            raise ValueError("age requested before the client-clock offset was estimated")
        return server_received_at - (issued_mono_client + self._offset_sec)
