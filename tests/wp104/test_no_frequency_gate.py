"""NORM-008 `ci_static`: zero paths where a frequency value drives a pass/fail decision.

The lock and the proof it is a lock live together. The static half asserts the property
over `backend/rtbench` and pins that the scanner behind it both fires on the banned shapes
and leaves the measurement shapes alone, because either half failing alone would leave the
first test green and worthless.

"The banned shapes" is the part that erodes. A frequency does not have to refuse a run to
decide one: it can drop the failing point before the judge sees it, or condition a
published permit, or select a gate state the scanner's vocabulary never listed. Those are
sinks, not special cases, and each is pinned here in every statement form the scanner
accepts — a sink covered in one form only can lose the other to a deletion no test notices.

The behavioural half is here for what no single expression states: a verdict that moves
because the band handed to it moved. That is pinned by holding the overrun rate fixed and
moving the frequency, and by requiring a measured failure to survive into the judged set.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import backend.rtbench.staticcheck as staticcheck_module
import tests.wp104.fixtures as fixtures_package
from backend.rtbench.constants import (
    GATE_STATE_PASS,
    GATE_STATE_RETRY_WITH_VARIANT,
    MAIN_PATH_OVERRUN_BUDGET,
)
from backend.rtbench.judge import BandPoint, judge_pg_rt_001a
from backend.rtbench.publish import _judged_band
from backend.rtbench.staticcheck import (
    GATE_STATE_LITERALS,
    SINK_ASSERT,
    SINK_FILTER,
    SINK_GATE_STATE,
    SINK_RAISE,
    SINK_VERDICT_FIELD,
    SINK_VERDICT_FUNCTION,
    FrequencyVerdictSite,
    scan_frequency_verdicts,
)
from sim.harness.harness import HarnessResult
from tests.wp104.fixtures import frequency_verdict_samples as samples

_RTBENCH_ROOT = Path(staticcheck_module.__file__).resolve().parent
_FIXTURE_ROOT = Path(fixtures_package.__file__).resolve().parent

_PASSING_OVERRUN = MAIN_PATH_OVERRUN_BUDGET / 2
_FAILING_OVERRUN = MAIN_PATH_OVERRUN_BUDGET * 10

# Well inside the 30-250 Hz main path, on both edges of it, and well outside on both
# sides — a frequency-driven verdict cannot agree across all six.
_SWEPT_FREQUENCIES_HZ = (1.0, 30.0, 125.0, 250.0, 300.0, 1000.0)

# The verdict field the permit controls publish; the sink label carries the field name.
_PERMIT_FIELD_NAME = "is_exit_permit"

# Four times the 250 Hz band ceiling: a sweep point no band filter anywhere on the path to
# the judge could keep.
_OUT_OF_BAND_SWEEP_HZ = 1000.0


def _line_span(function: Callable[..., Any]) -> tuple[int, int]:
    """The source line range one fixture function occupies.

    Read from the live object so moving code inside the fixture cannot silently turn a
    control green.

    Args:
        function: A fixture function.

    Returns:
        (tuple[int, int]) First and last one-based source lines.
    """
    lines, start = inspect.getsourcelines(function)
    return start, start + len(lines) - 1


def _sites_within(
    sites: list[FrequencyVerdictSite], function: Callable[..., Any]
) -> list[FrequencyVerdictSite]:
    """The reported sites falling inside one fixture function.

    Args:
        sites: Every site the scan reported.
        function: The fixture function to select for.

    Returns:
        (list[FrequencyVerdictSite]) The sites inside its source range.
    """
    low, high = _line_span(function)
    return [site for site in sites if low <= site.line <= high]


def test_rtbench_has_no_frequency_verdict_path() -> None:
    sites = scan_frequency_verdicts((_RTBENCH_ROOT,))
    assert sites == [], "frequency values drive a verdict here:\n" + "\n".join(
        str(site) for site in sites
    )


def test_scanner_flags_the_banned_shapes() -> None:
    sites = scan_frequency_verdicts((_FIXTURE_ROOT,))
    returns_a_verdict = samples.meets_target_shaped
    permit_field = f"{SINK_VERDICT_FIELD}:{_PERMIT_FIELD_NAME}"
    expected: tuple[tuple[Callable[..., Any], str], ...] = (
        (samples.enforce_target_shaped, SINK_RAISE),
        (samples.nested_raise_shaped, SINK_RAISE),
        (samples.else_branch_raise_shaped, SINK_RAISE),
        (samples.while_raise_shaped, SINK_RAISE),
        (samples.helper_abort_shaped, SINK_RAISE),
        (samples.exit_shaped, SINK_RAISE),
        (samples.hoisted_raise_shaped, SINK_RAISE),
        (samples.rehoisted_raise_shaped, SINK_RAISE),
        (returns_a_verdict, f"{SINK_VERDICT_FUNCTION}:{returns_a_verdict.__name__}"),
        (samples.assert_rate_shaped, SINK_ASSERT),
        (samples.gate_state_shaped, SINK_GATE_STATE),
        (samples.gate_state_branch_shaped, SINK_GATE_STATE),
        (samples.retry_state_shaped, SINK_GATE_STATE),
        (samples.hoisted_gate_state_shaped, SINK_GATE_STATE),
        (samples.band_filtered_shaped, SINK_FILTER),
        (samples.bar_filtered_shaped, SINK_FILTER),
        (samples.skip_out_of_band_shaped, SINK_FILTER),
        (samples.permit_field_shaped, permit_field),
        (samples.permit_keyword_shaped, permit_field),
        (samples.hoisted_permit_shaped, permit_field),
    )
    for function, sink in expected:
        flagged = _sites_within(sites, function)
        assert flagged, f"{function.__name__} was not flagged; the scanner cannot fire"
        assert {site.sink for site in flagged} == {sink}


def test_the_gate_state_vocabulary_is_this_packages_own() -> None:
    # A re-typed `PASS`/`FAIL` pair scans for a string this WP never writes: its two states
    # are PASS and RETRY_WITH_VARIANT, so the retry branch would select a gate state the
    # sink could not see. The set is read from the module that defines the states instead.
    assert frozenset({GATE_STATE_PASS, GATE_STATE_RETRY_WITH_VARIANT}) == GATE_STATE_LITERALS


def test_the_verdict_does_not_move_when_only_the_frequency_moves() -> None:
    failing = {
        target_hz: judge_pg_rt_001a((BandPoint(target_hz, _FAILING_OVERRUN),)).status
        for target_hz in _SWEPT_FREQUENCIES_HZ
    }
    assert set(failing.values()) == {GATE_STATE_RETRY_WITH_VARIANT}, (
        f"one overrun rate above the budget rendered more than one verdict: {failing}"
    )
    passing = {
        target_hz: judge_pg_rt_001a((BandPoint(target_hz, _PASSING_OVERRUN),)).status
        for target_hz in _SWEPT_FREQUENCIES_HZ
    }
    assert set(passing.values()) == {GATE_STATE_PASS}, (
        f"one overrun rate under the budget rendered more than one verdict: {passing}"
    )


def test_a_measured_failure_is_never_dropped_from_the_judged_set() -> None:
    band = tuple(BandPoint(target_hz, _FAILING_OVERRUN) for target_hz in _SWEPT_FREQUENCIES_HZ)
    verdict = judge_pg_rt_001a(band)
    assert verdict.failing_points == band
    assert verdict.band_points == band


def test_the_band_handed_to_the_judge_keeps_every_measured_point(
    harness_result: HarnessResult,
) -> None:
    # The judge drops nothing, so a band filter would have to sit upstream in
    # `publish._judged_band` instead. Pinning what arrives rather than where the filter is
    # not means moving it one function earlier does not move the property.
    result = replace(
        harness_result,
        fmax_sweep=[
            {"target_hz": _OUT_OF_BAND_SWEEP_HZ, "overrun_rate": _FAILING_OVERRUN},
            *harness_result.fmax_sweep,
        ],
    )
    judged = _judged_band(result)
    assert _OUT_OF_BAND_SWEEP_HZ in [point.target_hz for point in judged]
    assert len(judged) == len(result.fmax_sweep) + 1


def test_scanner_accepts_the_measurement_shapes() -> None:
    sites = scan_frequency_verdicts((_FIXTURE_ROOT,))
    for function in (
        samples.reject_nonpositive_rate,
        samples.resolve_rate_against_cap,
        samples.in_band,
        samples.band_label_shaped,
        samples.report_achieved_rate,
    ):
        flagged = _sites_within(sites, function)
        assert flagged == [], f"{function.__name__} is a measurement and must not be flagged: " + (
            "\n".join(str(site) for site in flagged)
        )
