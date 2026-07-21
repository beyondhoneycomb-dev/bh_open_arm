"""The top-level harness — run conditions 1-7 and derive the PG-RT-001a basis metrics.

This is the `PG-RT-001a` harness skeleton (`03` §5.1a): it runs the seven conditions
and computes the four quantities the gate is built on — the GIL contribution
(condition 4 minus condition 5, acceptance ④), the proof the load bites (condition 4
vs condition 1 distinguishability, acceptance ③), the RT-promotion gain (condition 6,
acceptance ⑤), and the harness self-overhead (acceptance ⑦). It also runs a frequency
sweep to publish overrun rate across the main-path band.

It pins no numeric verdict (acceptance ⑧). The provisional `f_max_python` it derives
is flagged `provisional: true`, is explicitly not a gate verdict, and names `WP-1-04`
as its judge and `PG-RT-001b` as the canonical gate that supersedes it — the honest
"best you can know without the rig" the split-gate design calls for (03 §5.1a).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from sim.harness.conditions import (
    ConditionResult,
    MeasurementConfig,
    condition_2_pattern_a,
    condition_3_full_teleop,
    condition_6_rt_promotion,
    condition_7_frame_count,
    loaded_same_process_histogram,
    run_interleaved_conditions,
)
from sim.harness.control_loop import DummyBinding, measure_self_overhead
from sim.harness.interleave import InterleavedMeasurement
from sim.harness.load_profile import LoadProfile
from sim.harness.statistics import DistributionComparison

# The main-path overrun budget: `03` §5.1a / `NFR-PRF-040` call ≤ 0.1% overrun a
# main-path pass. It is used only to *derive a provisional* f_max_python for the
# reader; the harness pins no verdict against it (acceptance ⑧) — the verdict is
# `WP-1-04`'s on real hardware, and `PG-RT-001b` supersedes it.
MAIN_PATH_OVERRUN_BUDGET = 1e-3


@dataclass
class HarnessResult:
    """Everything one harness run produced, before artifact assembly.

    Attributes:
        profile: The four-parameter load profile the run used.
        config: The measurement config.
        conditions: The seven condition results, in order.
        self_overhead: The instrument's per-sample overhead (acceptance ⑦).
        gil_contribution: Condition 4 vs condition 5, and their median difference.
        load_distinguishability: Condition 4 vs condition 1 — proof the load bites.
        fmax_sweep: Overrun rate across the swept main-path frequencies.
        fmax_python_provisional: The provisional, non-verdict f_max_python.
        connect_call_count: Times the harness connected a rig — 0 for `WP-0C-06`.
    """

    profile: LoadProfile
    config: MeasurementConfig
    conditions: list[ConditionResult]
    self_overhead: dict[str, float]
    gil_contribution: dict[str, Any]
    load_distinguishability: DistributionComparison
    fmax_sweep: list[dict[str, Any]]
    fmax_python_provisional: dict[str, Any]
    connect_call_count: int

    def condition(self, number: int) -> ConditionResult:
        """Return the result for a condition number.

        Args:
            number: The condition number, 1-7.

        Returns:
            (ConditionResult) That condition's result.

        Raises:
            KeyError: If no such condition ran.
        """
        for result in self.conditions:
            if result.number == number:
                return result
        raise KeyError(f"no condition {number} in result")


def _gil_contribution(interleaved: InterleavedMeasurement) -> dict[str, Any]:
    """Quantify the GIL contribution as condition 4 minus condition 5 (acceptance ④).

    Both distributions come from the same interleaved run, so their difference is the
    contention the shared GIL caused, not machine drift between two runs.

    Args:
        interleaved: The interleaved measurement carrying the same- and separate-process
            distributions and their drift-robust comparison.

    Returns:
        (dict[str, Any]) The two medians, their difference (the GIL contribution), and
        the rank-test comparison of the two distributions.
    """
    median_same = float(np.median(interleaved.same_process.samples))
    median_separate = float(np.median(interleaved.separate_process.samples))
    return {
        "median_same_process_sec": median_same,
        "median_separate_process_sec": median_separate,
        "gil_contribution_sec": median_same - median_separate,
        "comparison": interleaved.gil_contribution.as_record(),
    }


def _fmax_sweep(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> list[dict[str, Any]]:
    """Sweep the main-path band and record overrun rate at each frequency.

    Each sweep point re-runs the loaded, same-process measurement at that frequency,
    because overrun is a function of the target period.

    Args:
        profile: The load profile.
        config: The base measurement config (its sweep fields drive the sweep).
        dataset_dir: Directory the load writes under.

    Returns:
        (list[dict[str, Any]]) One record per swept frequency with its overrun rate.
    """
    sweep: list[dict[str, Any]] = []
    for frequency in config.sweep_frequencies_hz:
        point_config = replace(config, target_hz=frequency, tick_count=config.sweep_tick_count)
        histogram = loaded_same_process_histogram(profile, point_config, dataset_dir)
        period = point_config.period_sec
        sweep.append(
            {
                "target_hz": frequency,
                "period_sec": period,
                "overrun_tolerance": config.overrun_tolerance,
                "overrun_rate": histogram.overrun_rate(period, config.overrun_tolerance),
                "sample_count": histogram.count,
            }
        )
    return sweep


def _provisional_fmax_python(sweep: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive a provisional, non-verdict f_max_python from the sweep (acceptance ⑧).

    Args:
        sweep: The frequency sweep records.

    Returns:
        (dict[str, Any]) The highest swept frequency whose overrun cleared the budget,
        flagged `provisional: true` and `is_verdict: false`, naming `WP-1-04` as judge
        and `PG-RT-001b` as the canonical gate. `None` when no swept frequency cleared.
    """
    clearing = [
        point["target_hz"] for point in sweep if point["overrun_rate"] <= MAIN_PATH_OVERRUN_BUDGET
    ]
    value = max(clearing) if clearing else None
    return {
        "value_hz": value,
        "provisional": True,
        "is_verdict": False,
        "basis": "synthetic-gil-load",
        "overrun_budget": MAIN_PATH_OVERRUN_BUDGET,
        "judged_by": "WP-1-04",
        "canonical_gate": "PG-RT-001b",
        "note": (
            "provisional synthetic estimate, not a gate verdict; PG-RT-001a is judged "
            "by WP-1-04 on real hardware and PG-RT-001b (WP-3C-02) supersedes it"
        ),
    }


def run_harness(
    profile: LoadProfile,
    config: MeasurementConfig | None = None,
    dataset_dir: str | None = None,
) -> HarnessResult:
    """Run conditions 1-7 and the sweep, and derive the PG-RT-001a basis metrics.

    Args:
        profile: The four-parameter load profile.
        config: The measurement config; a default is used when None.
        dataset_dir: Directory the synthetic load writes under; a temp dir is used
            when None.

    Returns:
        (HarnessResult) The full run, ready for artifact assembly.
    """
    config = config or MeasurementConfig()

    if dataset_dir is None:
        with tempfile.TemporaryDirectory(prefix="gil-harness-") as tmp:
            return _run_harness_in(profile, config, tmp)
    Path(dataset_dir).mkdir(parents=True, exist_ok=True)
    return _run_harness_in(profile, config, dataset_dir)


def _run_harness_in(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> HarnessResult:
    """Run the harness with a concrete dataset directory.

    Args:
        profile: The load profile.
        config: The measurement config.
        dataset_dir: The directory the load writes under.

    Returns:
        (HarnessResult) The full run.
    """
    self_overhead = measure_self_overhead(config.self_overhead_iterations)

    interleaved, condition_1, condition_4, condition_5 = run_interleaved_conditions(
        profile, config, dataset_dir
    )
    conditions = [
        condition_1,
        condition_2_pattern_a(profile, config, dataset_dir),
        condition_3_full_teleop(profile, config, dataset_dir),
        condition_4,
        condition_5,
        condition_6_rt_promotion(profile, config, dataset_dir),
        condition_7_frame_count(config),
    ]

    gil_contribution = _gil_contribution(interleaved)
    load_distinguishability = interleaved.load_bite

    sweep = _fmax_sweep(profile, config, dataset_dir)
    fmax_python_provisional = _provisional_fmax_python(sweep)

    return HarnessResult(
        profile=profile,
        config=config,
        conditions=conditions,
        self_overhead=self_overhead,
        gil_contribution=gil_contribution,
        load_distinguishability=load_distinguishability,
        fmax_sweep=sweep,
        fmax_python_provisional=fmax_python_provisional,
        connect_call_count=DummyBinding().connect_call_count,
    )
