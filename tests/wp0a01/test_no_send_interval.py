"""Acceptance ⑧ — the max no-send interval stays under the RID-9 margin.

Because every tick emits exactly one frame, the interval between two consecutive
CAN sends is just the tick spacing — never two tick spacings, which would mean a
missed send. The trace's longest inter-send gap is measured across a run that mixes
accepted targets, stale holds, a latch, and a transition, and it stays strictly
below the configured RID-9 fail-safe margin (`12` NFR-SAF-007).
"""

from __future__ import annotations

import pytest

from backend.actuation import EmissionLabel, FaultInjectionHarness, TickTrace
from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC, TICK_INTERVAL_SEC


def test_max_no_send_interval_under_rid9_margin() -> None:
    """Across every emission type, no inter-send gap reaches the RID-9 margin."""
    harness = FaultInjectionHarness(
        trace=TickTrace(), lease_duration_sec=0.005, freshness_window_sec=0.005
    )

    # A run that visits all four emission kinds, every one of which still sends.
    for _ in range(20):
        harness.run_tick(publish=True, renew=True)  # accepted
    for _ in range(20):
        harness.run_tick(publish=False, renew=True)  # stale holds
    harness.begin_swap()
    harness.run_tick(publish=True, renew=True)  # transition hold
    harness.commit_swap()
    harness.latch()
    for _ in range(20):
        harness.run_tick(publish=True, renew=True)  # latch holds
    harness.acknowledge()
    for _ in range(20):
        harness.run_tick(publish=False, renew=False)  # lease-expiry holds

    trace = harness.trace
    assert isinstance(trace, TickTrace)

    # Every tick sent: no empty tick means the interval is one tick spacing.
    assert harness.can_writer.write_count == len(trace.entries)
    longest = trace.max_send_interval()
    assert longest < RID9_NO_SEND_MARGIN_SEC
    # And it is exactly the tick spacing, not a doubled (missed-send) gap.
    assert longest == pytest.approx(TICK_INTERVAL_SEC)
    # The run genuinely exercised holds as well as accepts.
    assert EmissionLabel.STALE_SOURCE_HOLD in trace.labels()
    assert EmissionLabel.SAFETY_LATCH_HOLD in trace.labels()
