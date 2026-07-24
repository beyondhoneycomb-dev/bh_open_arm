"""CG-4A-08b — a NaN/Inf action is not sent; the last valid action is held and counted.

`FR-INF-042`: LeRobot has no NaN/Inf check, so this is entirely ours. A non-finite
action must not be published; the last valid pose is held, a counter advances, and the
raw (non-finite) request stays recoverable in the dual log. A single rejection is not a
fault — the policy may recover — so the phase stays RUNNING.
"""

from __future__ import annotations

import math

from backend.actuation import FaultInjectionHarness
from backend.inference.runaway import InferencePhase
from tests.wp4a08.support import NEUTRAL_HOLD, flat_vector, make_detector


def test_nan_action_is_held_not_sent_and_counted() -> None:
    """A NaN action holds the last valid pose, bumps the counter, and stays recoverable."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)

    detector.process_action(flat_vector(5.0))
    valid_pose = detector.last_published
    assert valid_pose is not None

    nan_vector = flat_vector(5.0)
    nan_vector[3] = math.nan
    verdict = detector.process_action(nan_vector)

    assert verdict.nan_inf_rejected is True
    assert verdict.phase is InferencePhase.RUNNING
    assert detector.nan_inf_rejections == 1
    # Not sent: the mailbox holds the last valid pose, never the NaN request.
    published = harness.mailbox.take_latest()
    assert published is not None
    assert published.request == valid_pose
    # Raw recoverable: the dual record preserves the non-finite request verbatim.
    assert math.isnan(verdict.record.requested.values[3].value)
    assert not any(math.isnan(component.value) for component in verdict.record.accepted.values)


def test_inf_action_is_rejected_before_any_valid_action() -> None:
    """An Inf on the first tick holds the initial pose (`qh`), not the Inf action."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)

    inf_vector = flat_vector(0.0)
    inf_vector[0] = math.inf
    verdict = detector.process_action(inf_vector)

    assert verdict.nan_inf_rejected is True
    assert detector.nan_inf_rejections == 1
    published = harness.mailbox.take_latest()
    assert published is not None
    assert published.request == NEUTRAL_HOLD


def test_recovery_after_a_single_rejection_resumes_publishing() -> None:
    """A valid action after a rejection publishes again — one NaN does not latch a fault."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness)

    nan_vector = flat_vector(0.0)
    nan_vector[1] = math.nan
    detector.process_action(nan_vector)

    verdict = detector.process_action(flat_vector(2.0))
    assert verdict.phase is InferencePhase.RUNNING
    assert verdict.nan_inf_rejected is False
    assert verdict.is_hold_intent is False
    assert detector.nan_inf_rejections == 1
