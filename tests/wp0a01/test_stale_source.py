"""Acceptance ③ — a stale mailbox becomes STALE_SOURCE_HOLD on the next tick.

Detection latency is one tick: the tick right after a target's timestamp falls
outside the freshness window holds, no later. An empty mailbox is the same label
with its own reason code, and a fresh re-publish recovers to ACCEPTED_TARGET on the
next tick — so the hold is a response to staleness, not a latch.
"""

from __future__ import annotations

from backend.actuation import EmissionLabel, FaultInjectionHarness, ReasonCode, TickTrace

# One tick advance (0.001) already exceeds this window, so a target goes stale
# exactly one tick after the last publish — making the lag=1 claim exact.
NARROW_WINDOW_SEC = 0.0005


def test_empty_mailbox_holds_before_any_publish() -> None:
    """The first tick with nothing published is a STALE_SOURCE_HOLD / mailbox_empty."""
    harness = FaultInjectionHarness(trace=TickTrace(), freshness_window_sec=NARROW_WINDOW_SEC)
    emission = harness.run_tick(publish=False)
    assert emission.label is EmissionLabel.STALE_SOURCE_HOLD
    assert emission.reason is ReasonCode.MAILBOX_EMPTY


def test_stale_source_hold_on_the_very_next_tick() -> None:
    """A fresh accept, then one non-publishing tick, yields STALE with lag exactly 1."""
    harness = FaultInjectionHarness(trace=TickTrace(), freshness_window_sec=NARROW_WINDOW_SEC)

    fresh = harness.run_tick(publish=True)
    assert fresh.label is EmissionLabel.ACCEPTED_TARGET

    stale = harness.run_tick(publish=False)
    assert stale.label is EmissionLabel.STALE_SOURCE_HOLD
    assert stale.reason is ReasonCode.MAILBOX_STALE

    trace = harness.trace
    assert isinstance(trace, TickTrace)
    # Lag = 1: the accepted tick is immediately followed by the stale tick.
    labels = [entry.label for entry in trace.entries]
    accepted_at = labels.index(EmissionLabel.ACCEPTED_TARGET)
    assert labels[accepted_at + 1] is EmissionLabel.STALE_SOURCE_HOLD


def test_fresh_publish_recovers_from_stale() -> None:
    """Publishing again clears the hold on the next tick — staleness is not a latch."""
    harness = FaultInjectionHarness(trace=TickTrace(), freshness_window_sec=NARROW_WINDOW_SEC)
    harness.run_tick(publish=True)
    assert harness.run_tick(publish=False).label is EmissionLabel.STALE_SOURCE_HOLD
    assert harness.run_tick(publish=True).label is EmissionLabel.ACCEPTED_TARGET
