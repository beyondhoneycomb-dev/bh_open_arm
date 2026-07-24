"""SPINE §2-1 — the detector PUBLISHES a hold intent; the committed scheduler WRITES it.

`02c` §1.8: the runaway detector is a publisher, not a writer. On a fault it publishes a
hold intent to the mailbox and the committed `ActuationScheduler` emits the actual hold
frames — the detector never writes CAN and shares no file with the Wave-1 gateway. This
proves it structurally (the committed producer-CAN-access scan finds nothing under the
runaway tree) and behaviourally (a runaway's hold intent becomes exactly one scheduler
CAN write per tick, holding in place).
"""

from __future__ import annotations

from pathlib import Path

from backend.actuation import EmissionLabel, FaultInjectionHarness, find_producer_can_access
from backend.inference.runaway import InferencePhase
from tests.wp4a08.support import NEUTRAL_HOLD, flat_vector, make_detector

RUNAWAY_ROOT = Path("backend/inference/runaway")


def test_runaway_tree_never_reaches_the_can_handle() -> None:
    """The committed producer-CAN-access scan finds nothing in the runaway source tree."""
    assert find_producer_can_access(RUNAWAY_ROOT) == []


def test_runaway_hold_intent_becomes_one_scheduler_write() -> None:
    """A runaway publishes a hold intent the committed scheduler turns into one CAN write."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=None)

    verdict = detector.process_action(flat_vector(0.0), ee_velocity=5.0)
    assert verdict.phase is InferencePhase.FAULT
    # The published target is the hold intent (`qh`), not the offending action.
    assert detector.last_published == NEUTRAL_HOLD

    harness.renew()
    harness.advance()
    writes_before = harness.can_writer.write_count
    emission = harness.tick()

    assert emission.label is EmissionLabel.ACCEPTED_TARGET
    assert harness.can_writer.write_count == writes_before + 1


def test_faulted_hold_persists_across_scheduler_ticks_no_auto_resume() -> None:
    """While faulted the detector keeps publishing `qh` and the scheduler holds, one write/tick."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=None)
    detector.process_action(flat_vector(0.0), ee_velocity=5.0)

    for _ in range(4):
        outcome = detector.process_action(flat_vector(50.0), ee_velocity=5.0)
        assert outcome.phase is InferencePhase.FAULT
        assert detector.last_published == NEUTRAL_HOLD
        harness.renew()
        harness.advance()
        writes_before = harness.can_writer.write_count
        emission = harness.tick()
        assert emission.label is EmissionLabel.ACCEPTED_TARGET
        assert harness.can_writer.write_count == writes_before + 1
