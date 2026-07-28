"""The cycle-time measurement NORM-008 asks for in place of a frequency pass line.

The ruling is that no frequency decides pass or fail: the loop is measured, the numbers
are surfaced, and the judgment waits for the real figures (M-8). What has to be surfaced
is the distribution — median, 95th, 99th, maximum — the share of cycles that overran, and
the rate the loop is actually achieving.

The percentiles are not computed here. `CycleTimeHistogram.summary()` already owns them
and the artifact already publishes them inside the synthetic run, so this carries that
mapping through unchanged; recomputing it against a different percentile convention would
give the artifact two answers for the same p99. What this adds is the pairing — the
distribution, the overrun share and the achieved rate stated together at the top level,
where a reader looking for "what rate is it doing" finds one section instead of digging
through `synthetic_run.conditions`.

A run that collected no samples is refused rather than reported. An empty histogram's
summary carries only `count/min/mean/max`, so the percentiles the ruling requires are
absent, and publishing zeros for them would state a measurement that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.rtbench.constants import (
    CYCLE_TIME_NOTE,
    MEDIAN_DISTRIBUTION_KEY,
    REPORTED_DISTRIBUTION_KEYS,
)
from sim.harness.histogram import CycleTimeHistogram


@dataclass(frozen=True)
class CycleTimeMeasurement:
    """One operating point's cycle-time distribution, stated and not judged.

    Attributes:
        target_hz: The rate the loop was asked to run at.
        achieved_hz: The reciprocal of the median cycle time — what the loop is actually
            doing, which is the figure NORM-008 wants an operator to be able to read.
        sample_count: Cycles the distribution was taken over.
        distribution_sec: `CycleTimeHistogram.summary()` verbatim, in seconds.
        overrun_share: Fraction of cycles that exceeded the period plus its tolerance.
        is_verdict: Always False. NORM-008 rules that no frequency is a pass line, so
            this section renders none.
        note: The statement of that, carried beside the numbers.
    """

    target_hz: float
    achieved_hz: float
    sample_count: int
    distribution_sec: dict[str, float]
    overrun_share: float
    is_verdict: bool
    note: str

    def as_record(self) -> dict[str, Any]:
        """Serialize the measurement for the artifact.

        Returns:
            (dict[str, Any]) The rates, the distribution, the overrun share, and the
            explicit no-verdict flag.
        """
        return {
            "target_hz": self.target_hz,
            "achieved_hz": self.achieved_hz,
            "sample_count": self.sample_count,
            "distribution_sec": dict(self.distribution_sec),
            "overrun_share": self.overrun_share,
            "is_verdict": self.is_verdict,
            "note": self.note,
        }


def measure_cycle_time(
    histogram: CycleTimeHistogram,
    target_hz: float,
    overrun_tolerance: float,
) -> CycleTimeMeasurement:
    """Turn one condition's histogram into the surfaced cycle-time measurement.

    The overrun share is taken against `1 / target_hz`. That is the period the samples were
    collected under — every `ConditionResult.period_sec` and every sweep point's period is
    `MeasurementConfig.period_sec`, which is `1 / target_hz` — so deriving it rather than
    accepting it alongside removes the one way the reported rate and the period the share
    was computed against could contradict each other.

    Args:
        histogram: The condition's cycle-time samples.
        target_hz: The rate the loop was asked to run at.
        overrun_tolerance: Fractional slack above the period before a cycle counts as an
            overrun, passed through to the histogram that owns that rule.

    Returns:
        (CycleTimeMeasurement) The distribution, the overrun share, and the achieved rate.

    Raises:
        ValueError: If the summary is missing a figure the ruling requires, or the median
            cycle time is not positive — either way there is no measurement to report and
            zeros are not substituted for one.
    """
    distribution = histogram.summary()
    missing = [key for key in REPORTED_DISTRIBUTION_KEYS if key not in distribution]
    if missing:
        raise ValueError(
            f"cycle-time summary is missing {missing}; a run with no samples cannot be "
            "reported as a distribution of zeros (NORM-008 requires all four figures)"
        )
    median_sec = distribution[MEDIAN_DISTRIBUTION_KEY]
    if median_sec <= 0.0:
        raise ValueError(
            f"median cycle time is {median_sec} s; the achieved rate is undefined and is "
            "not reported as infinite"
        )
    return CycleTimeMeasurement(
        target_hz=target_hz,
        achieved_hz=1.0 / median_sec,
        sample_count=histogram.count,
        distribution_sec=distribution,
        overrun_share=histogram.overrun_rate(1.0 / target_hz, overrun_tolerance),
        is_verdict=False,
        note=CYCLE_TIME_NOTE,
    )
