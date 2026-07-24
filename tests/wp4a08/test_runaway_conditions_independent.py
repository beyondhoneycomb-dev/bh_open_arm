"""CG-4A-08a — each of the four runaway conditions independently drives P8, none masks another.

`FR-INF-043` requires four independent conditions, any one of which faults, each with
its own counter, and the negative branch (`02c` §1.8) forbids one condition masking
another. So each condition is injected in isolation and must reach P8 on its own with
`OA-INF-003` and itself recorded as the first trigger; and a tick that trips two at
once must advance *both* counters, proving no short-circuit.
"""

from __future__ import annotations

from backend.actuation import FaultInjectionHarness
from backend.inference.adapter import QueueMeter
from backend.inference.runaway import (
    RUNAWAY_ERROR_CODE,
    FaultKind,
    InferencePhase,
    RunawayCondition,
    RunawayDetector,
)
from tests.wp4a08.support import (
    drive_meter_starved,
    flat_vector,
    make_detector,
    tight_limits,
)


def _assert_faulted_on(detector: RunawayDetector, condition: RunawayCondition) -> None:
    """Assert the detector is in P8 attributed to `condition` as the first trigger."""
    assert detector.phase is InferencePhase.FAULT
    assert detector.fault_kind is FaultKind.RUNAWAY
    assert detector.fault_error_code == RUNAWAY_ERROR_CODE
    assert detector.first_trigger is condition
    assert detector.conditions.trigger_count(condition) >= 1


def test_clip_ratio_condition_alone_faults() -> None:
    """Condition ①: a sustained high clip ratio trips after the clip window and nothing else."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=tight_limits(-1.0, 1.0))

    verdict = None
    for _ in range(3):
        verdict = detector.process_action(flat_vector(100.0))

    assert verdict is not None
    assert verdict.triggered == frozenset({RunawayCondition.CLIP_RATIO})
    _assert_faulted_on(detector, RunawayCondition.CLIP_RATIO)
    assert detector.conditions.trigger_count(RunawayCondition.DELTA_Q) == 0
    assert detector.conditions.trigger_count(RunawayCondition.EE_VELOCITY) == 0
    assert detector.conditions.trigger_count(RunawayCondition.QUEUE_STARVATION) == 0


def test_delta_q_condition_alone_faults() -> None:
    """Condition ②: sustained per-tick jumps trip after the runaway window, unclamped."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=None)

    verdict = None
    for position in (0.0, 50.0, 100.0, 150.0):
        verdict = detector.process_action(flat_vector(position))

    assert verdict is not None
    assert verdict.triggered == frozenset({RunawayCondition.DELTA_Q})
    _assert_faulted_on(detector, RunawayCondition.DELTA_Q)
    assert detector.conditions.trigger_count(RunawayCondition.CLIP_RATIO) == 0


def test_ee_velocity_condition_alone_faults() -> None:
    """Condition ③: an over-limit EE speed trips instantly with an in-range action."""
    harness = FaultInjectionHarness()
    detector = make_detector(harness, joint_limits=None)

    verdict = detector.process_action(flat_vector(0.0), ee_velocity=5.0)

    assert verdict.triggered == frozenset({RunawayCondition.EE_VELOCITY})
    _assert_faulted_on(detector, RunawayCondition.EE_VELOCITY)
    assert detector.conditions.trigger_count(RunawayCondition.DELTA_Q) == 0


def test_queue_starvation_condition_alone_faults() -> None:
    """Condition ④: an exhaustion ratio over the limit trips from the committed meter."""
    harness = FaultInjectionHarness()
    meter = QueueMeter()
    drive_meter_starved(meter, starved=6, served=4)
    detector = make_detector(harness, meter=meter, joint_limits=None)

    verdict = detector.process_action(flat_vector(0.0))

    assert verdict.triggered == frozenset({RunawayCondition.QUEUE_STARVATION})
    _assert_faulted_on(detector, RunawayCondition.QUEUE_STARVATION)
    assert detector.conditions.trigger_count(RunawayCondition.CLIP_RATIO) == 0


def test_two_conditions_at_once_neither_masks_the_other() -> None:
    """Two instantaneous conditions on one tick advance both counters; first trigger is priority."""
    harness = FaultInjectionHarness()
    meter = QueueMeter()
    drive_meter_starved(meter, starved=6, served=4)
    detector = make_detector(harness, meter=meter, joint_limits=None)

    verdict = detector.process_action(flat_vector(0.0), ee_velocity=5.0)

    assert verdict.triggered == frozenset(
        {RunawayCondition.EE_VELOCITY, RunawayCondition.QUEUE_STARVATION}
    )
    assert detector.conditions.trigger_count(RunawayCondition.EE_VELOCITY) == 1
    assert detector.conditions.trigger_count(RunawayCondition.QUEUE_STARVATION) == 1
    # Priority order records EE_VELOCITY as first without suppressing the starvation counter.
    assert detector.first_trigger is RunawayCondition.EE_VELOCITY
