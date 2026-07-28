"""NORM-008's replacement for the pass line: the cycle-time distribution, surfaced.

The ruling asks for median / 95th / 99th / maximum plus the share of cycles that overran,
and for the operator to be able to read what rate the loop is actually achieving. These
tests pin that those five figures are produced, that they come out of the harness's own
summary rather than a second percentile definition, and that a run which collected no
samples is refused rather than reported as a well-formed measurement of zero.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.rtbench.constants import MEDIAN_DISTRIBUTION_KEY, REPORTED_DISTRIBUTION_KEYS
from backend.rtbench.cycle_time import measure_cycle_time
from sim.harness.histogram import CycleTimeHistogram

_TARGET_HZ = 100.0
_PERIOD_SEC = 1.0 / _TARGET_HZ
_OVERRUN_TOLERANCE = 0.05
_ON_TIME_COUNT = 90
_OVERRUN_COUNT = 10

# The line the histogram counts against: a cycle overruns when it exceeds
# `period * (1 + tolerance)`.
_OVERRUN_THRESHOLD_SEC = _PERIOD_SEC * (1.0 + _OVERRUN_TOLERANCE)

# Samples sit a tenth of a percent either side of that line rather than a whole multiple
# away. A sample set spread wide keeps its overrun count under any period within a factor
# of roughly three, which lets a wrong period report the right share; these reclassify as
# soon as the period moves at all, so the share can only come out right for `1 / target_hz`.
_JUST_UNDER_THRESHOLD = 0.999
_JUST_OVER_THRESHOLD = 1.001


def _mixed_samples() -> np.ndarray:
    """A sample set bracketing the overrun line, with a known number of overruns.

    Returns:
        (np.ndarray) Cycle times in seconds.
    """
    on_time = [_OVERRUN_THRESHOLD_SEC * _JUST_UNDER_THRESHOLD] * _ON_TIME_COUNT
    overrun = [_OVERRUN_THRESHOLD_SEC * _JUST_OVER_THRESHOLD] * _OVERRUN_COUNT
    return np.array(on_time + overrun, dtype=np.float64)


def test_the_four_reported_figures_are_the_ones_the_ruling_names() -> None:
    # NORM-008: "median / 95th / 99th / maximum". Shrinking the tuple silently drops a
    # figure the ruling requires, so the required set is stated here, not read back.
    assert set(REPORTED_DISTRIBUTION_KEYS) == {"p50", "p95", "p99", "max"}
    assert MEDIAN_DISTRIBUTION_KEY in REPORTED_DISTRIBUTION_KEYS


def test_the_overrun_share_is_taken_against_the_reported_target_rate() -> None:
    # The period is derived from target_hz rather than accepted beside it, so a caller
    # cannot report one rate while the share was measured against a different period.
    histogram = CycleTimeHistogram(_mixed_samples())
    measurement = measure_cycle_time(
        histogram=histogram,
        target_hz=_TARGET_HZ,
        overrun_tolerance=_OVERRUN_TOLERANCE,
    )
    assert measurement.overrun_share == pytest.approx(
        histogram.overrun_rate(1.0 / measurement.target_hz, _OVERRUN_TOLERANCE)
    )


def test_measurement_reports_the_four_figures_and_the_overrun_share() -> None:
    samples = _mixed_samples()
    measurement = measure_cycle_time(
        histogram=CycleTimeHistogram(samples),
        target_hz=_TARGET_HZ,
        overrun_tolerance=_OVERRUN_TOLERANCE,
    )

    distribution = measurement.distribution_sec
    assert set(REPORTED_DISTRIBUTION_KEYS) <= set(distribution)
    ordered = [distribution[key] for key in REPORTED_DISTRIBUTION_KEYS]
    assert ordered == sorted(ordered)

    expected_share = float(np.count_nonzero(samples > _OVERRUN_THRESHOLD_SEC)) / samples.size
    assert measurement.overrun_share == pytest.approx(expected_share)
    assert expected_share > 0.0  # the sample set must actually exercise the overrun path

    assert measurement.sample_count == samples.size
    assert measurement.achieved_hz == pytest.approx(1.0 / float(np.median(samples)))
    assert measurement.target_hz == _TARGET_HZ
    assert measurement.is_verdict is False


def test_record_carries_the_distribution_and_declares_itself_no_verdict() -> None:
    record = measure_cycle_time(
        histogram=CycleTimeHistogram(_mixed_samples()),
        target_hz=_TARGET_HZ,
        overrun_tolerance=_OVERRUN_TOLERANCE,
    ).as_record()
    assert record["is_verdict"] is False
    assert set(REPORTED_DISTRIBUTION_KEYS) <= set(record["distribution_sec"])
    assert record["note"]


def test_empty_measurement_is_refused_not_zeroed() -> None:
    # An empty histogram's summary carries only count/min/mean/max, so the percentiles the
    # ruling requires are absent — reporting that as a distribution of zeros would state a
    # measurement that never happened.
    with pytest.raises(ValueError, match="p50"):
        measure_cycle_time(
            histogram=CycleTimeHistogram(np.array([], dtype=np.float64)),
            target_hz=_TARGET_HZ,
            overrun_tolerance=_OVERRUN_TOLERANCE,
        )


def test_a_zero_median_is_refused_rather_than_an_infinite_achieved_rate() -> None:
    with pytest.raises(ValueError, match="median"):
        measure_cycle_time(
            histogram=CycleTimeHistogram(np.zeros(_ON_TIME_COUNT, dtype=np.float64)),
            target_hz=_TARGET_HZ,
            overrun_tolerance=_OVERRUN_TOLERANCE,
        )
