"""NORM-013 — the cycle-time distribution and the missed-target share are always reported.

The ruling (`docs/v1/plan/normalization/ledger.yaml` NORM-013) refuses a lower-bound loop-rate
ratio: the only citable precedent is ALOHA's 84%, measured on other hardware, and pinning it
here would make it this project's pass line by accident. What replaces it is a report — p50,
p95, p99 and the share of cycles that overran the target — plus an fps the operator can lower,
because without a floor the target is the only thing anyone can move when a machine cannot hold
30 fps.

Every target rate here comes from the fixture or from a named operator choice. A literal 30
would re-pin the number the ruling declined to bless.
"""

from __future__ import annotations

from dataclasses import replace
from statistics import pstdev

import pytest

from backend.recorder.quality.constants import MIN_SELECTABLE_FPS, NANOS_PER_SECOND
from backend.recorder.quality.metrics import (
    CycleTimeError,
    cycle_time_stats,
    validate_target_fps,
)
from backend.recorder.quality.report import (
    GateOutcome,
    QualityThresholds,
    build_report,
    evaluate,
)
from contracts.fixtures.synthetic_dataset import FIXTURE_FPS, build_synthetic_dataset
from tests.wp3b12.support import (
    CYCLE_BASE_MONO_NS,
    frames_from_dataset,
    frames_with_cycle_instants,
)

# The longest whole-nanosecond cycle that still fits the fixture target period. One more
# nanosecond is an overrun, which is what makes the spared/missed boundary testable.
_ON_TARGET_NS = NANOS_PER_SECOND // FIXTURE_FPS

# A 100 ms cycle: three times the fixture target period, and exactly the period of the
# lowered operator target below — so the same series is an overrun at one rate and not at
# the other.
_OVERRUN_CYCLE_NS = 100_000_000
_LOWERED_OPERATOR_FPS = 10

# A single wider cycle mixed into a uniform series, so the spread is nonzero and the
# percentiles have somewhere to separate.
_SPREAD_CYCLE_NS = 120_000_000

# An operator target above the fixture rate. Present only to show `validate_target_fps`
# imposes no ceiling either.
_HIGH_OPERATOR_FPS = 120

# Half the 10 Hz a 100 ms cycle achieves, and a microsecond against a spread measured in
# milliseconds: a measured report clears the first bar and fails the second, so an UNSET on
# the unmeasured report cannot be a blanket verdict.
_LOOP_RATE_FLOOR_HZ = 5.0
_JITTER_CEILING_S = 1e-6

# The rate a 100 ms cycle achieves. A third of the fixture target, so a report that handed
# the target back instead of measuring lands on a visibly different number rather than
# inside a tolerance.
_OVERRUN_CYCLE_RATE_HZ = NANOS_PER_SECOND / _OVERRUN_CYCLE_NS

# A uniform cycle series has exactly zero spread; this absorbs float noise, not a bar.
_ZERO_JITTER_TOLERANCE_S = 1e-9

# Two spreads straddling a ceiling placed midway between them, close enough that halving or
# doubling the graded number crosses it. A zero-versus-large pair cannot separate a gate that
# reads the spread from one that reads a rescaled copy, or one that compares it in the wrong
# unit: zero stays zero under any factor, and a spread four orders above the ceiling stays
# above it.
_NARROW_SPREAD_EXCESS_NS = 10_000_000
_WIDE_SPREAD_EXCESS_NS = 15_000_000
_MAX_SEPARABLE_SPREAD_RATIO = 2.0

# The three positions an unstamped frame can hold. An interior gap splices the cycles
# either side into one long one, which reads as a measurement; an end gap instead shortens
# the episode the distribution describes, and nothing in the report says so.
_LEADING_FRAME_POSITION = 0
_INTERIOR_FRAME_POSITION = 2
_TRAILING_FRAME_POSITION = -1


def test_cycle_time_distribution_is_reported() -> None:
    """NORM-013: p50/p95/p99 and the maximum are reported for a measured episode."""
    intervals = [_ON_TARGET_NS] * 9 + [_OVERRUN_CYCLE_NS]
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)

    report = build_report(
        frames_with_cycle_instants(dataset, intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )
    stats = report.cycle_time

    assert stats.interval_count == len(intervals)
    assert stats.p50_s == pytest.approx(_ON_TARGET_NS / NANOS_PER_SECOND)
    assert stats.max_s == pytest.approx(_OVERRUN_CYCLE_NS / NANOS_PER_SECOND)
    assert stats.p50_s < stats.p95_s < stats.p99_s <= stats.max_s
    assert stats.achieved_rate_hz() == pytest.approx(NANOS_PER_SECOND / _ON_TARGET_NS)


def test_achieved_rate_is_the_measured_one_not_the_configured_target() -> None:
    """NORM-013: the reported rate comes from the stamped cycles, not from `target_fps`.

    A series three times slower than the target is what separates the two. An on-target
    series cannot: there the measured rate and the configured one coincide to within any
    tolerance, so a report handing back its own input reads as a measurement.
    """
    intervals = [_OVERRUN_CYCLE_NS] * 6
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)

    stats = build_report(
        frames_with_cycle_instants(dataset, intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    ).cycle_time

    assert stats.target_fps == FIXTURE_FPS
    assert stats.achieved_rate_hz() == pytest.approx(_OVERRUN_CYCLE_RATE_HZ)
    assert stats.achieved_rate_hz() != pytest.approx(float(FIXTURE_FPS))


def test_the_serialised_rate_is_the_measured_one_not_the_configured_target() -> None:
    """NORM-013: the sidecar's `achieved_rate_hz` comes from the stamped cycles too.

    `to_dict` is the artefact a human reads, and it is a second expression of the same
    claim: pinning the accessor alone leaves the serialised field free to hand back
    `target_fps` under a measured name. Both expected values are derived from the stamped
    series rather than read back off the report.

    The series is deliberately not uniform. Where every cycle is the same length the median
    and the maximum coincide, and a serialised rate taken from the wrong end of the
    distribution reads as correct — so the spread carries the distinction the assertion
    needs, and the maximum is pinned separately to keep the two apart.
    """
    intervals = [_OVERRUN_CYCLE_NS] * 4 + [_SPREAD_CYCLE_NS] * 2
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)

    body = build_report(
        frames_with_cycle_instants(dataset, intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    ).to_dict()["cycle_time"]

    assert body["target_fps"] == FIXTURE_FPS
    assert body["p50_s"] == pytest.approx(_OVERRUN_CYCLE_NS / NANOS_PER_SECOND)
    assert body["max_s"] == pytest.approx(_SPREAD_CYCLE_NS / NANOS_PER_SECOND)
    assert body["achieved_rate_hz"] == pytest.approx(_OVERRUN_CYCLE_RATE_HZ)
    assert body["achieved_rate_hz"] != pytest.approx(float(FIXTURE_FPS))


def test_jitter_is_the_spread_of_the_measured_cycles() -> None:
    """NORM-013: the reported spread is the standard deviation of the stamped cycles.

    `evaluate` grades this number against a caller-supplied ceiling, so a wrong one flips a
    verdict. The expected value is derived from the stamped series here rather than read
    back off the report.
    """
    steady_intervals = [_ON_TARGET_NS] * 6
    spread_intervals = [_ON_TARGET_NS] * 3 + [_SPREAD_CYCLE_NS] * 3
    dataset = build_synthetic_dataset(frame_count=len(steady_intervals) + 1)

    steady = build_report(
        frames_with_cycle_instants(dataset, steady_intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    ).cycle_time
    spread = build_report(
        frames_with_cycle_instants(dataset, spread_intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    ).cycle_time

    assert steady.jitter_std_s == pytest.approx(0.0, abs=_ZERO_JITTER_TOLERANCE_S)
    assert spread.jitter_std_s == pytest.approx(pstdev(spread_intervals) / NANOS_PER_SECOND)


def test_the_jitter_gate_grades_the_spread_and_no_other_cycle_measure() -> None:
    """⑥ `max_jitter_std_s` is compared against the spread, so a wrong measure flips a verdict.

    Both series overrun the target by the same median, so every other cycle-time number the
    report carries — median, maximum, achieved rate, missed-target share — is either equal
    across the two or already past the ceiling on both. Only the spread separates them, and
    only a gate bound to the spread returns two different verdicts.
    """
    steady_intervals = [_OVERRUN_CYCLE_NS] * 6
    # Six intervals put the median on the fourth-shortest, so widening the last two leaves
    # the median where the steady series has it and moves the spread alone.
    spread_intervals = [_OVERRUN_CYCLE_NS] * 4 + [_SPREAD_CYCLE_NS] * 2
    dataset = build_synthetic_dataset(frame_count=len(steady_intervals) + 1)
    thresholds = QualityThresholds(max_jitter_std_s=_JITTER_CEILING_S)

    steady = build_report(
        frames_with_cycle_instants(dataset, steady_intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )
    spread = build_report(
        frames_with_cycle_instants(dataset, spread_intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )

    assert steady.cycle_time.p50_s == pytest.approx(spread.cycle_time.p50_s)
    assert steady.cycle_time.jitter_std_s == pytest.approx(0.0, abs=_ZERO_JITTER_TOLERANCE_S)
    assert spread.cycle_time.jitter_std_s > _JITTER_CEILING_S
    assert evaluate(steady, thresholds)["jitter"] is GateOutcome.PASS
    assert evaluate(spread, thresholds)["jitter"] is GateOutcome.FAIL


def test_the_jitter_gate_turns_on_how_large_the_spread_is() -> None:
    """⑥ The gate compares the spread's value to the ceiling, not merely its presence.

    Both series carry a nonzero spread, the ceiling sits between them, and the two are
    within `_MAX_SEPARABLE_SPREAD_RATIO` of each other. That is what a steady-versus-spread
    pair cannot test: a steady series has a spread of exactly zero, which stays below any
    ceiling however it is rescaled, and a spread milliseconds wide stays above a
    microsecond ceiling the same way. Between those two extremes every unit slip and every
    stray factor on the way into the comparison is invisible.
    """
    narrow_intervals = [_OVERRUN_CYCLE_NS] * 5 + [_OVERRUN_CYCLE_NS + _NARROW_SPREAD_EXCESS_NS]
    wide_intervals = [_OVERRUN_CYCLE_NS] * 5 + [_OVERRUN_CYCLE_NS + _WIDE_SPREAD_EXCESS_NS]
    dataset = build_synthetic_dataset(frame_count=len(narrow_intervals) + 1)
    narrow_spread_s = pstdev(narrow_intervals) / NANOS_PER_SECOND
    wide_spread_s = pstdev(wide_intervals) / NANOS_PER_SECOND
    thresholds = QualityThresholds(max_jitter_std_s=(narrow_spread_s + wide_spread_s) / 2)

    narrow = build_report(
        frames_with_cycle_instants(dataset, narrow_intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )
    wide = build_report(
        frames_with_cycle_instants(dataset, wide_intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )

    assert narrow.cycle_time.p50_s == pytest.approx(wide.cycle_time.p50_s)
    assert wide_spread_s < _MAX_SEPARABLE_SPREAD_RATIO * narrow_spread_s
    assert evaluate(narrow, thresholds)["jitter"] is GateOutcome.PASS
    assert evaluate(wide, thresholds)["jitter"] is GateOutcome.FAIL


def test_missed_target_share_counts_overruns_and_spares_on_target_cycles() -> None:
    """NORM-013: the share counts cycles past the target period and only those."""
    overruns = 2
    intervals = [_ON_TARGET_NS] * 8 + [_OVERRUN_CYCLE_NS] * overruns
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)

    stats = build_report(
        frames_with_cycle_instants(dataset, intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    ).cycle_time

    assert stats.interval_count == len(intervals)
    assert stats.missed_target_intervals == overruns
    assert stats.missed_target_share == pytest.approx(overruns / len(intervals))

    bumped = [_ON_TARGET_NS + 1] * 8 + [_OVERRUN_CYCLE_NS] * overruns
    bumped_stats = build_report(
        frames_with_cycle_instants(dataset, bumped),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    ).cycle_time

    assert bumped_stats.missed_target_intervals == len(bumped)


def test_operator_may_lower_the_target_so_the_same_run_stops_missing() -> None:
    """NORM-013: the operator moves the target; the measurement underneath does not move."""
    intervals = [_OVERRUN_CYCLE_NS] * 6
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)
    frames = frames_with_cycle_instants(dataset, intervals)

    at_fixture = build_report(frames, dataset.sidecar, dataset.config, FIXTURE_FPS).cycle_time
    at_lowered = build_report(
        frames, dataset.sidecar, dataset.config, _LOWERED_OPERATOR_FPS
    ).cycle_time

    assert at_fixture.missed_target_intervals == len(intervals)
    assert at_lowered.missed_target_intervals == 0
    assert at_fixture.target_fps == FIXTURE_FPS
    assert at_lowered.target_fps == _LOWERED_OPERATOR_FPS
    assert at_fixture.p50_s == at_lowered.p50_s


def test_unmeasured_cycle_time_reports_no_distribution_and_still_records_the_target() -> None:
    """A recorder that stamps no cycle instant reports None, never a fabricated 0.0."""
    intervals = [_ON_TARGET_NS] * 5
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)

    grid_only = build_report(
        frames_from_dataset(dataset), dataset.sidecar, dataset.config, FIXTURE_FPS
    )

    assert grid_only.cycle_time.interval_count == 0
    assert grid_only.cycle_time.p50_s is None
    assert grid_only.cycle_time.missed_target_intervals is None
    assert grid_only.cycle_time.missed_target_share is None
    assert grid_only.cycle_time.achieved_rate_hz() is None
    body = grid_only.to_dict()["cycle_time"]
    assert body["target_fps"] == FIXTURE_FPS
    assert body["p50_s"] is None
    assert body["achieved_rate_hz"] is None

    measured = build_report(
        frames_with_cycle_instants(dataset, intervals),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )

    assert measured.cycle_time.p50_s is not None
    assert measured.cycle_time.missed_target_share is not None


def test_a_single_stamped_frame_reports_nothing_measured_rather_than_raising() -> None:
    """One instant is zero intervals: a defined, empty distribution, not an arithmetic error.

    A rate needs two instants to form one interval. Differencing a lone instant leaves an
    empty array, and every reduction over it raises — so the short-circuit has to cover one
    instant, not just none. A one-frame episode is what a recorder produces when the
    operator stops it immediately, and the band has to describe it rather than refuse it.
    """
    stats = cycle_time_stats((CYCLE_BASE_MONO_NS,), FIXTURE_FPS)

    assert stats.interval_count == 0
    assert stats.p50_s is None
    assert stats.jitter_std_s is None
    assert stats.missed_target_intervals is None
    assert stats.missed_target_share is None
    assert stats.achieved_rate_hz() is None
    assert stats.target_fps == FIXTURE_FPS

    dataset = build_synthetic_dataset(frame_count=1)
    single = build_report(
        frames_with_cycle_instants(dataset, []),
        dataset.sidecar,
        dataset.config,
        FIXTURE_FPS,
    )

    outcomes = evaluate(single, QualityThresholds(min_loop_rate_hz=_LOOP_RATE_FLOOR_HZ))

    assert single.frame_count == 1
    assert single.duration_s == 0.0
    assert single.cycle_time.interval_count == 0
    assert outcomes["loop_rate"] is GateOutcome.UNSET


def test_unmeasured_cycle_time_grades_unset_even_when_thresholds_are_supplied() -> None:
    """An absent measurement cannot become a FAIL on the rate and a PASS on the jitter."""
    intervals = [_OVERRUN_CYCLE_NS] * 8 + [_SPREAD_CYCLE_NS]
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)
    thresholds = QualityThresholds(
        min_loop_rate_hz=_LOOP_RATE_FLOOR_HZ, max_jitter_std_s=_JITTER_CEILING_S
    )

    unmeasured = evaluate(
        build_report(frames_from_dataset(dataset), dataset.sidecar, dataset.config, FIXTURE_FPS),
        thresholds,
    )
    measured = evaluate(
        build_report(
            frames_with_cycle_instants(dataset, intervals),
            dataset.sidecar,
            dataset.config,
            FIXTURE_FPS,
        ),
        thresholds,
    )

    assert unmeasured["loop_rate"] is GateOutcome.UNSET
    assert unmeasured["jitter"] is GateOutcome.UNSET
    assert measured["loop_rate"] is GateOutcome.PASS
    assert measured["jitter"] is GateOutcome.FAIL


def test_target_fps_refuses_only_a_rate_with_no_period() -> None:
    """NORM-013: the sole refusal is arithmetic — a rate with no period. No floor above it."""
    for refused in (0, -5):
        with pytest.raises(CycleTimeError):
            validate_target_fps(refused)

    for accepted in (MIN_SELECTABLE_FPS, _LOWERED_OPERATOR_FPS, FIXTURE_FPS, _HIGH_OPERATOR_FPS):
        assert validate_target_fps(accepted) == accepted

    # The target is checked before the instants, so an episode with nothing measured still
    # refuses a rate that has no period rather than reporting against it.
    with pytest.raises(CycleTimeError):
        cycle_time_stats((), 0)


def test_backwards_cycle_instants_are_refused() -> None:
    """A monotonic clock cannot go back or stand still; either is broken data, not a slow cycle."""
    forward = (CYCLE_BASE_MONO_NS, CYCLE_BASE_MONO_NS + _ON_TARGET_NS)

    assert cycle_time_stats(forward, FIXTURE_FPS).interval_count == 1

    with pytest.raises(CycleTimeError):
        cycle_time_stats(tuple(reversed(forward)), FIXTURE_FPS)
    with pytest.raises(CycleTimeError):
        cycle_time_stats((CYCLE_BASE_MONO_NS, CYCLE_BASE_MONO_NS), FIXTURE_FPS)


@pytest.mark.parametrize(
    "unstamped_positions",
    [
        (_LEADING_FRAME_POSITION,),
        (_INTERIOR_FRAME_POSITION,),
        (_TRAILING_FRAME_POSITION,),
        (_LEADING_FRAME_POSITION, _INTERIOR_FRAME_POSITION, _TRAILING_FRAME_POSITION),
    ],
)
def test_partly_stamped_episode_is_refused_rather_than_spliced(
    unstamped_positions: tuple[int, ...],
) -> None:
    """An unstamped frame is a gap in the instant series, never a cycle that ran long.

    Dropping an interior one and differencing the frames either side reports the gap as one
    long cycle, which lands in the percentiles and the missed-target share as if it had been
    measured. Trimming a leading or trailing one instead measures a shorter episode than the
    one recorded, and the interval count is the only trace — against a frame count nothing
    here compares it to.

    The multi-gap case is the one a guard written around a single dropout lets through, and
    it is the worse of the two: more frames absent means a longer spliced cycle, reported at
    the same confidence as a measured one.
    """
    intervals = [_ON_TARGET_NS] * 5
    dataset = build_synthetic_dataset(frame_count=len(intervals) + 1)
    stamped = frames_with_cycle_instants(dataset, intervals)
    partly = list(stamped)
    for position in unstamped_positions:
        partly[position] = replace(partly[position], cycle_mono_ns=None)

    with pytest.raises(CycleTimeError):
        build_report(partly, dataset.sidecar, dataset.config, FIXTURE_FPS)

    fully = build_report(stamped, dataset.sidecar, dataset.config, FIXTURE_FPS)
    assert fully.cycle_time.interval_count == len(intervals)
