"""Acceptance ⑤: the PG-RT-001a verdict and its frozen, order-forced retry escalation.

A pass needs every main-path point under the 0.1% budget; a failure escalates through
exactly the enumerated variants, in the forced order, and never invents a new one.
"""

from __future__ import annotations

from backend.rtbench.constants import (
    FINAL_GATE,
    GATE_STATE_PASS,
    GATE_STATE_RETRY_WITH_VARIANT,
    MAIN_PATH_OVERRUN_BUDGET,
    PROVISIONAL_GATE,
)
from backend.rtbench.judge import (
    FORCED_VARIANT_ESCALATION,
    BandPoint,
    band_points_from_sweep,
    judge_pg_rt_001a,
)

_PASSING = MAIN_PATH_OVERRUN_BUDGET / 2
_FAILING = MAIN_PATH_OVERRUN_BUDGET * 10

# The forced order is canon: process separation before RT promotion (PREEMPT_RT
# cannot fix GIL contention in Python), then worker separation as the terminal fallback.
_EXPECTED_ORDER = ("process_separation", "pattern_a", "rt_promotion", "worker_separation")


def test_all_within_budget_passes() -> None:
    band = (BandPoint(60.0, _PASSING), BandPoint(125.0, _PASSING), BandPoint(250.0, _PASSING))
    verdict = judge_pg_rt_001a(band)
    assert verdict.status == GATE_STATE_PASS
    assert verdict.passed
    assert verdict.failing_points == ()
    assert verdict.escalation == ()


def test_any_main_path_failure_retries_with_the_forced_escalation() -> None:
    band = (BandPoint(60.0, _PASSING), BandPoint(125.0, _FAILING), BandPoint(250.0, _PASSING))
    verdict = judge_pg_rt_001a(band)
    assert verdict.status == GATE_STATE_RETRY_WITH_VARIANT
    assert not verdict.passed
    assert verdict.failing_points == (BandPoint(125.0, _FAILING),)
    assert verdict.escalation == FORCED_VARIANT_ESCALATION


def test_escalation_order_is_frozen_and_not_invented() -> None:
    keys = tuple(variant.key for variant in FORCED_VARIANT_ESCALATION)
    assert keys == _EXPECTED_ORDER
    # process separation strictly precedes RT promotion.
    assert keys.index("process_separation") < keys.index("rt_promotion")
    # worker separation is terminal and is a retry, not a CAN-ownership transfer.
    terminal = FORCED_VARIANT_ESCALATION[-1]
    assert terminal.key == "worker_separation"
    assert "CAN-ownership transfer" in terminal.rationale


def test_out_of_band_point_cannot_fail_the_verdict() -> None:
    # A 300 Hz point is above the 250 Hz band ceiling: it is carried but not judged.
    band = (BandPoint(125.0, _PASSING), BandPoint(300.0, _FAILING))
    verdict = judge_pg_rt_001a(band)
    assert verdict.status == GATE_STATE_PASS
    # only the in-band point is retained in the judged set.
    assert [point.target_hz for point in verdict.band_points] == [125.0]


def test_band_points_from_sweep_reads_the_harness_record() -> None:
    sweep = [
        {"target_hz": 60.0, "overrun_rate": 0.0},
        {"target_hz": 250.0, "overrun_rate": 0.02},
    ]
    points = band_points_from_sweep(sweep)
    assert points == (BandPoint(60.0, 0.0), BandPoint(250.0, 0.02))


def test_record_is_provisional_and_names_its_superseding_gate() -> None:
    verdict = judge_pg_rt_001a((BandPoint(125.0, _PASSING),))
    record = verdict.as_record()
    assert record["gate"] == PROVISIONAL_GATE
    assert record["provisional"] is True
    assert record["superseded_by"] == FINAL_GATE
    assert record["is_wave1_exit_permit"] is True
