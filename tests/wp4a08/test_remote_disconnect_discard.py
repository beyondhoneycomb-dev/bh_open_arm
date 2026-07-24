"""CG-4A-08e — a remote disconnect discards the queue immediately, holds, runs no open-loop.

`FR-INF-046`: on a remote disconnect the residual action queue must be discarded at
once (executing it open-loop, with no observation, is a runaway), a hold intent must be
published, and zero open-loop ticks may occur. This fills the queue, disconnects, and
requires the residual to be 0 the same call, a hold published, and no open-loop
execution — before or after, in the latched fault.
"""

from __future__ import annotations

from dataclasses import replace

from backend.actuation import FaultInjectionHarness
from backend.inference.runaway import FaultKind, InferencePhase
from tests.wp4a08.support import flat_vector, healthy_remote, make_detector


def _chunk(n: int) -> list[list[float]]:
    """Return `n` distinct 16-wide action vectors to fill the residual queue."""
    return [flat_vector(float(index)) for index in range(1, n + 1)]


def test_transport_disconnect_discards_queue_and_publishes_hold() -> None:
    """A transport loss zeroes the residual immediately and publishes a hold intent."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)
    detector.load_queue(_chunk(5))
    assert detector.queue_residual == 5

    verdict = detector.on_remote_health(replace(healthy_remote(), transport_ok=False))

    assert verdict.queue_residual_after == 0
    assert detector.queue_residual == 0
    assert verdict.hold_intent_published is True
    assert detector.phase is InferencePhase.FAULT
    assert detector.fault_kind is FaultKind.REMOTE_DISCONNECT
    assert verdict.error_code == "OA-INF-001"
    # The hold intent reached the mailbox.
    published = harness.mailbox.take_latest()
    assert published is not None


def test_no_open_loop_execution_after_disconnect() -> None:
    """After a disconnect no queued action executes without an observation (0 open-loop)."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)
    detector.load_queue(_chunk(4))

    detector.on_remote_health(replace(healthy_remote(), action=[]))
    assert detector.open_loop_execution_ticks == 0
    assert detector.queue_residual == 0

    # Faulted ticks keep holding; no residual is ever drained open-loop.
    for _ in range(5):
        outcome = detector.process_action(flat_vector(9.0))
        assert outcome.phase is InferencePhase.FAULT
        assert outcome.is_hold_intent is True
    assert detector.open_loop_execution_ticks == 0
    assert detector.queue_residual == 0


def test_empty_action_disconnect_uses_queue_family_code() -> None:
    """An empty-action disconnect holds with the queue-exhausted code, still discarding."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)
    detector.load_queue(_chunk(3))

    verdict = detector.on_remote_health(replace(healthy_remote(), action=[]))

    assert verdict.error_code == "OA-INF-002"
    assert verdict.is_network is False
    assert verdict.queue_residual_after == 0
    assert detector.phase is InferencePhase.FAULT


def test_healthy_remote_leaves_queue_and_phase_untouched() -> None:
    """A healthy remote neither discards the queue nor faults."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)
    detector.load_queue(_chunk(2))

    verdict = detector.on_remote_health(healthy_remote(action=flat_vector(1.0)))

    assert verdict.disconnect_class is None
    assert verdict.hold_intent_published is False
    assert detector.queue_residual == 2
    assert detector.phase is InferencePhase.RUNNING
