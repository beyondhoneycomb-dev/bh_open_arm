"""CG-4A-08c — a clamp where requested != accepted logs BOTH; the raw request is recoverable.

`FR-INF-047`: `send_action` returns the post-clip value, so without preserving the
pre-gate request the policy's intent is lost forever and 4C cannot tell "bad policy"
from "gate clamped". This exercises a real clamp (one joint driven out of its limit)
and requires the dual record to keep the raw request beside the clamped accepted action.
"""

from __future__ import annotations

from backend.actuation import FaultInjectionHarness
from backend.inference.runaway import InferencePhase
from tests.wp4a08.support import flat_vector, make_detector, single_joint_limit


def test_clamp_logs_both_raw_and_accepted() -> None:
    """One clamped joint below the runaway ratio: both values logged, raw recoverable."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=single_joint_limit(0, -1.0, 1.0))

    requested_vector = flat_vector(0.0)
    requested_vector[0] = 100.0
    verdict = detector.process_action(requested_vector)

    # One clamped joint out of sixteen stays under clip_ratio_max, so no fault.
    assert verdict.phase is InferencePhase.RUNNING
    record = verdict.record
    assert record.clamp_detected is True
    # Raw request recoverable: the pre-gate 100 deg is preserved verbatim.
    assert record.requested.values[0].value == 100.0
    # Accepted is the post-gate clamp actually sent.
    assert record.accepted.values[0].value == 1.0
    # Unclamped joints are identical in both channels.
    assert record.requested.values[1] == record.accepted.values[1]
    assert record.requested.values != record.accepted.values


def test_clean_action_logs_equal_channels() -> None:
    """An in-range action logs requested == accepted (no clamp), still both present."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=single_joint_limit(0, -1000.0, 1000.0))

    verdict = detector.process_action(flat_vector(3.0))

    assert verdict.record.clamp_detected is False
    assert verdict.record.requested.values == verdict.record.accepted.values


def test_recorder_retains_every_tick_raw_recoverable() -> None:
    """Across ticks, the recorder keeps every raw request, each recoverable in order."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=single_joint_limit(0, -1.0, 1.0))

    for position in (10.0, 20.0, 30.0):
        vector = flat_vector(0.0)
        vector[0] = position
        detector.process_action(vector)

    raws = [record.requested.values[0].value for record in detector.recorder.records]
    assert raws == [10.0, 20.0, 30.0]
    accepteds = [record.accepted.values[0].value for record in detector.recorder.records]
    assert accepteds == [1.0, 1.0, 1.0]
