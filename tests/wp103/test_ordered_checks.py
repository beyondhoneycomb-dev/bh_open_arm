"""Acceptance ③ / ④ / ⑨ — eight distinct reasons, enforced order, clip vs stop.

The filter is the ordered eight-check pipeline. Each check, when triggered alone,
must return its own distinct reason (③) — a merged "rejected" is forbidden. Running
the checks in any order but the canonical one is itself a rejection (④). And a
position-limit violation clips-and-proceeds while a step-delta violation stops (⑨),
the `JointPosChecker` / `JointDeltaPosChecker` distinction.
"""

from __future__ import annotations

from backend.actuation import (
    CHECK_ORDER,
    CheckStage,
    FilterInput,
    MotionHistory,
    SafetyFilter,
    SafetyReason,
)
from contracts.units import Deg
from tests.wp103.conftest import TEST_DT_SEC, TEST_FRESHNESS_SEC, degs, make_limits


def _filter_input(
    request: tuple[Deg, ...],
    *,
    present: tuple[Deg, ...] = (Deg(0.0), Deg(0.0)),
    prev_velocity: tuple[float, ...] | None = None,
    prev_accel: tuple[float, ...] | None = None,
    source_age_sec: float = 0.0,
    calibrated: bool = True,
    collision_latched: bool = False,
    require_stopped: bool = False,
) -> FilterInput:
    """Build a filter input with healthy defaults, overriding one knob per check."""
    return FilterInput(
        request=request,
        history=MotionHistory(
            present_deg=present,
            prev_velocity_rad_s=prev_velocity,
            prev_accel_rad_s2=prev_accel,
        ),
        dt_sec=TEST_DT_SEC,
        source_age_sec=source_age_sec,
        freshness_window_sec=TEST_FRESHNESS_SEC,
        calibrated=calibrated,
        collision_latched=collision_latched,
        require_stopped=require_stopped,
        feedforward_torque_nm=None,
    )


def test_each_check_returns_its_own_distinct_reason() -> None:
    """Triggering each of the eight checks alone yields eight distinct reasons (③)."""
    filt = SafetyFilter(make_limits())
    tight_velocity = SafetyFilter(make_limits(velocity_rad_s=0.5))
    tight_accel = SafetyFilter(make_limits(accel_rad_s2=5.0))

    outcomes = {
        CheckStage.UNIT: filt.evaluate(_filter_input(degs(1.0, 1.0, 1.0))),
        CheckStage.ZERO: filt.evaluate(_filter_input(degs(1.0, 1.0), calibrated=False)),
        CheckStage.LIMIT: filt.evaluate(_filter_input(degs(120.0, 0.0))),
        CheckStage.FRESHNESS: filt.evaluate(_filter_input(degs(1.0, 1.0), source_age_sec=1.0)),
        CheckStage.WORKSPACE_COLLISION: filt.evaluate(
            _filter_input(degs(1.0, 1.0), collision_latched=True)
        ),
        CheckStage.SLEW: tight_velocity.evaluate(_filter_input(degs(30.0, 0.0))),
        CheckStage.JERK: tight_accel.evaluate(
            _filter_input(degs(10.0, 0.0), prev_velocity=(0.0, 0.0))
        ),
        CheckStage.STOPPED: filt.evaluate(_filter_input(degs(5.0, 0.0), require_stopped=True)),
    }

    reasons = {stage: outcome.reason for stage, outcome in outcomes.items()}
    # Every triggered check produced a reason that is not NONE.
    assert all(reason is not SafetyReason.NONE for reason in reasons.values())
    # And every reason is distinct: no merged "rejected" collapses two checks into one.
    assert len(set(reasons.values())) == len(reasons)
    # The reasons are the ones each stage is meant to raise.
    assert reasons[CheckStage.UNIT] is SafetyReason.UNIT_MISMATCH
    assert reasons[CheckStage.ZERO] is SafetyReason.ZERO_UNCALIBRATED
    assert reasons[CheckStage.LIMIT] is SafetyReason.JOINT_LIMIT
    assert reasons[CheckStage.FRESHNESS] is SafetyReason.STALE_SOURCE
    assert reasons[CheckStage.WORKSPACE_COLLISION] is SafetyReason.COLLISION_LATCH
    assert reasons[CheckStage.SLEW] is SafetyReason.VELOCITY_LIMIT
    assert reasons[CheckStage.JERK] is SafetyReason.ACCEL_LIMIT
    assert reasons[CheckStage.STOPPED] is SafetyReason.NOT_STOPPED


def test_shuffled_check_order_is_rejected() -> None:
    """Running the checks in any order but the canonical one is a rejection (④)."""
    filt = SafetyFilter(make_limits())
    shuffled = tuple(reversed(CHECK_ORDER))
    outcome = filt.evaluate(_filter_input(degs(1.0, 1.0)), check_order=shuffled)
    assert outcome.rejected
    assert outcome.reason is SafetyReason.ORDER_VIOLATION


def test_canonical_order_is_accepted() -> None:
    """The canonical order runs the pipeline (the order guard is not over-eager)."""
    filt = SafetyFilter(make_limits())
    outcome = filt.evaluate(_filter_input(degs(1.0, 1.0)), check_order=CHECK_ORDER)
    assert not outcome.rejected
    assert outcome.reason is SafetyReason.NONE


def test_position_limit_clips_and_proceeds_step_delta_stops() -> None:
    """A position-limit clips and is admitted; a step-delta stops outright (⑨)."""
    # Operational ±10°, loose velocity/step: a request to 50° clips to 10° and is admitted.
    clip_filter = SafetyFilter(
        make_limits(operational_deg=10.0, velocity_rad_s=1.0e6, step_delta_rad=100.0)
    )
    clip = clip_filter.evaluate(_filter_input(degs(50.0, 0.0)))
    assert not clip.rejected
    assert clip.accepted is not None
    assert clip.accepted[0].value == 10.0
    assert clip.reason is SafetyReason.JOINT_LIMIT

    # Tight step-delta, wide operational: the same-size move stops, admitting nothing.
    stop_filter = SafetyFilter(
        make_limits(operational_deg=180.0, velocity_rad_s=1.0e6, step_delta_rad=0.3)
    )
    stop = stop_filter.evaluate(_filter_input(degs(50.0, 0.0)))
    assert stop.rejected
    assert stop.accepted is None
    assert stop.reason is SafetyReason.STEP_DELTA
