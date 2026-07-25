"""Builders that ground the WP-4C-04 gates on committed types, not on mocks.

The dual records the correlation engine reads are built by the committed WP-4A-08
`DualActionRecorder` — a genuine joint-limit clamp goes through the real
`clamp_request`, and a NaN reject through the real `record_held` — so the tests exercise
the same records a live rollout produces, never a hand-forged `SafetyOverride`. The
runaway / disconnect / counter signals are the injected faults the gates pull; that is
what the taxonomy classifies.
"""

from __future__ import annotations

import math

from backend.actuation import FaultInjectionHarness, JointLimit, MailboxProducer
from backend.eval.taxonomy import EpisodeSignals
from backend.inference.adapter import QueueMeter
from backend.inference.runaway import (
    DisconnectClass,
    DualActionRecord,
    DualActionRecorder,
    FaultKind,
    RunawayDetector,
    metering_placeholder_thresholds,
)
from contracts.action import (
    BIMANUAL_ACTION_DIM,
    AcceptedPositionAction,
    RequestedPositionAction,
)
from contracts.units import Deg

_NEUTRAL_DEG = 0.0
_CLAMP_LOW_DEG = -1.0
_CLAMP_HIGH_DEG = 1.0
_OUT_OF_LIMIT_DEG = 100.0
# metering_placeholder_thresholds() trips CLIP_RATIO after this many consecutive fully
# clamped ticks (placeholder clip_window). One over shows the fault reliably.
_CLIP_WINDOW_TICKS = 3


def _request(value: float) -> RequestedPositionAction:
    """Return a 16-wide request with every joint at `value` degrees."""
    return RequestedPositionAction(values=tuple(Deg(value) for _ in range(BIMANUAL_ACTION_DIM)))


def _tight_limits() -> tuple[tuple[Deg, Deg], ...]:
    """Return a symmetric per-joint limit that clamps any large request."""
    return tuple((Deg(_CLAMP_LOW_DEG), Deg(_CLAMP_HIGH_DEG)) for _ in range(BIMANUAL_ACTION_DIM))


def joint_limit_clamp_record() -> DualActionRecord:
    """Return a real dual record whose request was clamped for a joint limit.

    Returns:
        (DualActionRecord) `clamp_detected` True, `clamp_reason` JOINT_LIMIT.
    """
    recorder = DualActionRecorder()
    return recorder.record(_request(_OUT_OF_LIMIT_DEG), _tight_limits())


def nan_reject_record() -> DualActionRecord:
    """Return a real dual record for a NaN reject: request replaced by a held pose.

    This record also has `clamp_detected` True (the held pose differs from the
    non-finite request), but its `clamp_reason` is NONE — the case the engine must not
    mis-tag as `POLICY_OUT_OF_BOUNDS`.

    Returns:
        (DualActionRecord) A held record with `clamp_reason` NONE.
    """
    recorder = DualActionRecorder()
    nan_request = RequestedPositionAction(
        values=tuple(Deg(math.nan) for _ in range(BIMANUAL_ACTION_DIM))
    )
    held = AcceptedPositionAction(
        values=tuple(Deg(_NEUTRAL_DEG) for _ in range(BIMANUAL_ACTION_DIM))
    )
    return recorder.record_held(nan_request, held)


def clean_record() -> DualActionRecord:
    """Return a real in-range dual record with no clamp."""
    recorder = DualActionRecorder()
    return recorder.record(_request(0.5), _tight_limits())


def runaway_clamp_detector() -> RunawayDetector:
    """Drive a real detector to a joint-limit-clamp runaway and return it at fault.

    Feeds fully out-of-limit actions through the committed `RunawayDetector` until the
    CLIP_RATIO condition trips (P3 -> P8). The detector ends in FAULT with `fault_kind`
    RUNAWAY and a dual log full of genuine joint-limit clamps — the exact terminal state
    `EpisodeSignals.from_detector` reads, so the consumption is of committed types.

    Returns:
        (RunawayDetector) The detector in FAULT after a real runaway.
    """
    limits: tuple[JointLimit | None, ...] = _tight_limits()
    harness = FaultInjectionHarness(joint_limits=limits)
    detector = RunawayDetector(
        producer=MailboxProducer("wp4c04-taxonomy", harness.mailbox, harness.clock),
        meter=QueueMeter(),
        thresholds=metering_placeholder_thresholds(),
        initial_hold=_request(_NEUTRAL_DEG),
        joint_limits=limits,
    )
    detector.begin_episode()
    for _ in range(_CLIP_WINDOW_TICKS):
        detector.process_action([_OUT_OF_LIMIT_DEG for _ in range(BIMANUAL_ACTION_DIM)])
    return detector


def signals(
    dual_records: tuple[DualActionRecord, ...] = (),
    fault_kind: FaultKind | None = None,
    disconnect_class: DisconnectClass | None = None,
    nan_inf_rejections: int = 0,
    queue_exhaustion_ratio: float = 0.0,
    safety_stop_count: int = 0,
    collision_count: int = 0,
    torque_limit_hits: int = 0,
) -> EpisodeSignals:
    """Build an `EpisodeSignals` with healthy defaults, overriding only what a test sets.

    Returns:
        (EpisodeSignals) The synthetic episode's terminal signals.
    """
    return EpisodeSignals(
        dual_records=dual_records,
        fault_kind=fault_kind,
        disconnect_class=disconnect_class,
        nan_inf_rejections=nan_inf_rejections,
        queue_exhaustion_ratio=queue_exhaustion_ratio,
        safety_stop_count=safety_stop_count,
        collision_count=collision_count,
        torque_limit_hits=torque_limit_hits,
    )
