"""Acceptance ⑭ / ⑲ — Cat-2 stop is one hold frame, and every tick emits one of four.

These re-confirm the actuation spine (`WP-0A-01` ①) integrated with the gateway: the
stop path is a single MIT hold frame, never a torque cut, and between torque-on and
torque-off there is no empty tick — every tick emits exactly one of the four labels
and performs exactly one CAN write.
"""

from __future__ import annotations

from backend.actuation import (
    EmissionLabel,
    FaultInjectionHarness,
    TickTrace,
)

_FOUR_LABELS = frozenset(EmissionLabel)


def test_cat2_stop_is_exactly_one_hold_frame() -> None:
    """A latched (Cat-2) stop emits exactly one MIT hold frame per tick (⑭)."""
    harness = FaultInjectionHarness()
    harness.run_tick()  # a normal accepted tick first
    harness.latch()

    before = harness.can_writer.write_count
    emission = harness.run_tick(publish=False, renew=False)
    after = harness.can_writer.write_count

    assert emission.label is EmissionLabel.SAFETY_LATCH_HOLD
    # Exactly one MIT frame was written for the stop — not zero (a dropped arm) and
    # not a torque-disable burst.
    assert after - before == 1


def test_every_tick_emits_one_of_four_labels() -> None:
    """Across an adversarial run, every tick emits one of the four and writes once (⑲)."""
    trace = TickTrace()
    harness = FaultInjectionHarness(trace=trace)
    ticks = 500
    harness.run_random(ticks, seed=1903)

    # One CAN write per tick over the whole run: no empty tick, no double write. The
    # scheduler raises inside the loop on a violation, so reaching here is the proof.
    assert harness.can_writer.write_count == ticks
    assert len(trace.entries) == ticks
    # Every recorded label is one of the four; nothing else was ever emitted.
    assert trace.labels() <= _FOUR_LABELS


def test_hold_persists_every_tick_while_source_is_absent() -> None:
    """With no producer publishing, every tick still emits a hold — never silence (⑲)."""
    harness = FaultInjectionHarness()
    for _ in range(50):
        emission = harness.run_tick(publish=False, renew=True)
        assert emission.is_hold
    # Fifty held ticks, fifty frames — the stream never stopped.
    assert harness.can_writer.write_count == 50
