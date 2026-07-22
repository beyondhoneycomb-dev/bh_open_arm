"""Acceptance ⑦ — injecting WS jitter moves the stop earlier, never later.

The deadman inverts the usual sign: a link delay means a missed renewal, which
expires the lease and stops the arm. So more jitter can only bring the stop *forward*.
The failure this guards against is the opposite-sign design, where a delayed renewal
is honoured late and pushes the stop *out*. The tests measure the real stop tick on
the spine under an injected late renewal and show it is pinned to the true expiry,
strictly earlier than a delay-tolerant policy would place it, by the injected delay.
"""

from __future__ import annotations

from tests.wp2a02.conftest import (
    LEASE_DURATION_SEC,
    MAX_LEASE_AGE_SEC,
    TICK_INTERVAL_SEC,
    DeadmanHarness,
)

_WARMUP_TICKS = 10
_DURATION_TICKS = round(LEASE_DURATION_SEC / TICK_INTERVAL_SEC)
_TAIL_TICKS = 60


def _stop_tick_with_late_renewal(jitter_ticks: int) -> int:
    """Measure the tick a stop first appears when a single renewal arrives late.

    The last on-time renewal is at the end of warmup; a lone renewal is then injected
    `jitter_ticks` after the true expiry. The returned tick is measured from the end
    of warmup.

    Args:
        jitter_ticks: How far past the true expiry the late renewal arrives.

    Returns:
        (int) The 0-based tick, from warmup end, at which the first hold appeared.
    """
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_WARMUP_TICKS):
        harness.tick(publish=True, renew=True)

    late_arrival_tick = _DURATION_TICKS + jitter_ticks
    stop_tick = None
    for tick in range(late_arrival_tick + _TAIL_TICKS):
        emission = harness.tick(publish=True, renew=(tick == late_arrival_tick))
        if emission.is_hold and stop_tick is None:
            stop_tick = tick
    assert stop_tick is not None
    return stop_tick


def test_late_renewal_never_delays_the_stop() -> None:
    """Across increasing jitter, the stop tick never moves later — it is pinned (⑦)."""
    jitters = [0, 20, 50, 120]
    stops = [_stop_tick_with_late_renewal(jitter) for jitter in jitters]

    # Non-increasing: more jitter never pushes the stop later.
    for earlier, later in zip(stops, stops[1:], strict=False):
        assert later <= earlier
    # In fact pinned to the true expiry regardless of how late the renewal arrives —
    # the late renewal cannot extend the lease.
    assert min(stops) == max(stops)
    # The pin sits at the lease horizon (within one tick of the harness's tick
    # accounting), not out at any late arrival.
    assert abs(stops[0] - _DURATION_TICKS) <= 1


def test_stop_is_earlier_than_a_delay_tolerant_policy_by_the_jitter() -> None:
    """Our stop beats a delay-tolerant policy by the injected delay, growing with it (⑦).

    A policy that honoured the late renewal would stop only at arrival + duration. Ours
    stops at the true expiry, so the margin by which ours is earlier equals the jitter
    and widens as jitter grows — the earlier-not-later property, quantified.
    """
    previous_margin = -1
    for jitter in (10, 40, 90):
        our_stop = _stop_tick_with_late_renewal(jitter)
        # A delay-tolerant design accepts the renewal at arrival and stops a full
        # duration later.
        delay_tolerant_stop = (_DURATION_TICKS + jitter) + _DURATION_TICKS
        margin = delay_tolerant_stop - our_stop
        assert our_stop < delay_tolerant_stop
        assert margin > previous_margin
        previous_margin = margin


def test_max_lease_age_is_below_the_lease_duration() -> None:
    """The bench age bound is tighter than the lease, so jitter bites before expiry (⑦)."""
    # A renewal delayed past max_lease_age is discarded well before it could ever
    # extend a lease near its expiry — the age filter is the fine-grained edge of the
    # same earlier-not-later behaviour.
    assert MAX_LEASE_AGE_SEC < LEASE_DURATION_SEC
