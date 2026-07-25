"""CG-5-05a — a control-class round-trip latency measurement is produced, no threshold.

The gate is "the measurement exists", not "the latency passed". This proves the p99 of
telemetry and command is produced under max load, that no pass/fail is rendered, and
that a class which delivered nothing is refused rather than reported as a zero (a zero
would read as a passing measurement that never ran).
"""

from __future__ import annotations

import pytest

from backend.loadtest import LoadRun, measure_roundtrip
from backend.loadtest.constants import ROUNDTRIP_TAIL_PERCENTILE
from backend.loadtest.harness import ClassResult, LoadProfile, run_load
from backend.loadtest.hol_judge import CONTROL_CLASSES
from contracts.ws.schema import WsFrameType


def test_p99_is_produced_for_each_control_class(saturated_run: LoadRun) -> None:
    measurement = measure_roundtrip(saturated_run)
    for frame_type in CONTROL_CLASSES:
        profile = measurement.profiles[frame_type]
        assert profile.sample_count > 0
        assert ROUNDTRIP_TAIL_PERCENTILE in profile.percentiles_sec
        assert profile.tail_sec > 0.0


def test_measurement_renders_no_pass_fail(saturated_run: LoadRun) -> None:
    measurement = measure_roundtrip(saturated_run)
    # The measurement object carries the percentiles and an explicit no-threshold note;
    # it exposes no pass/fail field, because none is decided here.
    assert "no pass/fail" in measurement.no_threshold_note
    assert not hasattr(measurement, "passed")


def test_missing_samples_are_refused_not_zeroed(max_load_profile: LoadProfile) -> None:
    # A degenerate run of zero duration delivers no control frames. The measurement
    # must refuse rather than substitute a zero p99.
    empty = run_load(max_load_profile, duration_sec=0.0009, step_sec=0.001)
    # Force the command class empty to exercise the refusal deterministically.
    empty.results[WsFrameType.COMMAND] = ClassResult(frame_type=WsFrameType.COMMAND)
    with pytest.raises(ValueError, match="no frames"):
        measure_roundtrip(empty)
