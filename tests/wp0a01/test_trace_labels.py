"""Acceptance ⑨ — the trace records all four labels and their reason codes, in full.

A deterministic scenario drives every emission type and every reason code, and the
trace is checked to have kept each one — and to have kept a record for every tick,
not a sample: the record count equals the CAN write count. Each record also carries
the MIT batch it wrote, which is the `executedMitCommand` audit channel of the
interface contract ⑥.
"""

from __future__ import annotations

from backend.actuation import (
    MIT_BATCH_WIDTH,
    EmissionLabel,
    FaultInjectionHarness,
    ReasonCode,
    TickTrace,
)


def test_trace_carries_all_labels_and_reason_codes_unsampled() -> None:
    """Every label and reason code is recorded, once per tick, with its MIT batch."""
    harness = FaultInjectionHarness(
        trace=TickTrace(),
        lease_duration_sec=0.002,
        freshness_window_sec=0.0005,
    )

    harness.run_tick(publish=False)  # STALE_SOURCE_HOLD / mailbox_empty
    harness.run_tick(publish=True, renew=True)  # ACCEPTED_TARGET / fresh
    harness.run_tick(publish=False, renew=True)  # STALE_SOURCE_HOLD / mailbox_stale

    # Fresh mailbox but no renewal -> lease expiry.
    for _ in range(20):
        if harness.run_tick(publish=True, renew=False).reason is ReasonCode.LEASE_EXPIRED:
            break

    harness.begin_swap()
    harness.run_tick(publish=True, renew=True)  # MODE_TRANSITION_HOLD / producer_swap
    harness.commit_swap()

    harness.latch()
    harness.run_tick(publish=True, renew=True)  # SAFETY_LATCH_HOLD / safety_latch
    harness.acknowledge()

    trace = harness.trace
    assert isinstance(trace, TickTrace)

    # All four labels present.
    assert trace.labels() == set(EmissionLabel)
    # All six reason codes present.
    assert trace.reason_codes() == set(ReasonCode)

    # Full, not sampled: one record per tick, and every record is a real audit frame.
    assert len(trace.entries) == harness.can_writer.write_count
    assert len(trace.entries) == harness.scheduler.tick_index
    for entry in trace.entries:
        assert len(entry.batch) == MIT_BATCH_WIDTH
