"""The expiry-to-latch bridge — turning lease expiry into a one-way SAFETY latch.

This is the piece that makes the deadman a *latch*, not a hold. The Wave-1 decider
already emits a hold when `LeaseManager.is_expired` is True (its `LEASE_EXPIRED`
branch), but that hold clears itself the moment a renewal makes the lease live
again — an arm that "stops briefly and then moves on its own" (`02b` §1.0). The
monitor closes that hole: on the tick the lease first lapses, it signals the caller
to engage the scheduler's `SafetyLatch`, which only an operator ack can clear.

Server clock only. `observe` is given a boolean already computed from the server
monotonic clock; this class never sees `issued_mono_client` or any client time, so
the expiry path holds zero client-clock references (acceptance ⑥).

The edge, not the level, is what it reports. Latching on the *level* (expired) would
re-latch on every tick, and — worse — would re-latch in the window after a re-arm
ack but before the first new renewal, when the lease is legitimately still expired,
making re-arm impossible. So it latches only on the transition from live to expired,
and `arm` resets it to "not yet live" so a freshly re-armed, not-yet-renewed lease
holds without latching until it has actually been live and then lapses.
"""

from __future__ import annotations


class DeadmanMonitor:
    """Reports the single tick on which lease expiry should engage the safety latch."""

    def __init__(self) -> None:
        """Create a monitor that has not yet seen the lease live.

        A lease that has never been renewed is expired but must not latch: at
        torque-on the arm is held pending the operator's first renewal, and a latch
        there would demand a re-arm before the deadman was ever taken.
        """
        self._was_live = False

    def arm(self) -> None:
        """Reset to "not yet live" after a (re-)arm.

        After an operator re-arm the lease is still expired until the first renewal
        of the new generation arrives. Clearing `was_live` here stops the monitor
        from immediately re-latching that legitimately-expired lease, which would
        make re-arm unable to complete.
        """
        self._was_live = False

    def observe(self, is_expired: bool, latched: bool) -> bool:
        """Advance the live/expired edge and report whether to latch now.

        Args:
            is_expired: Whether the lease has lapsed as of now, judged on the server
                clock. The only expiry input; no client time reaches this method.
            latched: Whether the safety latch is already engaged.

        Returns:
            (bool) True on exactly the tick expiry should engage the latch — the
            first tick the lease is expired after having been live and while not
            already latched. False otherwise, including every tick while latched and
            every tick before the lease has ever been live.
        """
        if not is_expired:
            self._was_live = True
            return False
        if latched or not self._was_live:
            return False
        # Falling edge: was live, now expired, not yet latched. Consume the edge so
        # the latch is engaged exactly once.
        self._was_live = False
        return True
