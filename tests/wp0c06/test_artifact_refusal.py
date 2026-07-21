"""Acceptance ② and ⑥ — the artifact is refused when it would be dishonest.

Two publication guards are hard refusals, not warnings: an artifact whose four load
parameters are not all recorded (②) and one that would publish summary statistics
without the full distribution (⑥). This suite builds a synthetic — but structurally
complete — harness result and shows the guards fire, without running the timing
harness.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from sim.harness.artifact import ArtifactRefusedError, build_artifact
from sim.harness.conditions import ConditionResult, MeasurementConfig
from sim.harness.harness import HarnessResult
from sim.harness.histogram import CycleTimeHistogram
from sim.harness.load_profile import LoadProfile
from sim.harness.statistics import compare_distributions


def _timing_condition(number: int, key: str) -> ConditionResult:
    """A timing condition carrying a small but complete distribution."""
    samples = np.linspace(4.0e-3, 4.2e-3, 120)
    return ConditionResult(
        number=number,
        key=key,
        title=key,
        is_timing=True,
        histogram=CycleTimeHistogram(samples),
        period_sec=4.0e-3,
    )


def _make_result() -> HarnessResult:
    """Build a structurally complete harness result for the guard tests."""
    conditions = [
        _timing_condition(1, "condition_1_idle"),
        _timing_condition(2, "condition_2_pattern_a"),
        _timing_condition(3, "condition_3_full_teleop"),
        _timing_condition(4, "condition_4_gil_load_same_process"),
        _timing_condition(5, "condition_5_process_separation"),
        _timing_condition(6, "condition_6_rt_promotion"),
        ConditionResult(
            number=7,
            key="condition_7_frame_count",
            title="frame count",
            is_timing=False,
            extra={"frames_per_cycle_model": 32, "provisional": True},
        ),
    ]
    comparison = compare_distributions(np.linspace(1, 2, 50), np.linspace(1, 2, 50))
    return HarnessResult(
        profile=LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024),
        config=MeasurementConfig(),
        conditions=conditions,
        self_overhead={"iterations": 500.0, "min": 5e-8, "median": 6e-8, "mean": 6e-8},
        gil_contribution={"gil_contribution_sec": 1e-4, "comparison": comparison.as_record()},
        load_distinguishability=comparison,
        fmax_sweep=[{"target_hz": 250.0, "overrun_rate": 0.5}],
        fmax_python_provisional={"value_hz": None, "provisional": True, "is_verdict": False},
        connect_call_count=0,
    )


class _IncompleteProfile:
    """A stand-in profile that fails to record one of the four parameters."""

    def as_record(self) -> dict[str, Any]:
        """Return a record missing `serialize_bytes_per_tick`."""
        return {
            "stream_count": 5,
            "resolution": [320, 240],
            "png_write_bytes_per_frame": 32 * 1024,
        }


def test_complete_result_publishes() -> None:
    """A complete result publishes, carrying full per-condition distributions."""
    artifact = build_artifact(_make_result())
    assert artifact["wp_id"] == "WP-0C-06"
    timing = [c for c in artifact["conditions"] if c["is_timing"]]
    assert timing and all(c["distribution"]["raw_samples"] for c in timing)


def test_unrecorded_profile_is_refused() -> None:
    """A run whose four load parameters are not all recorded is refused (②)."""
    result = _make_result()
    result.profile = _IncompleteProfile()  # type: ignore[assignment]
    with pytest.raises(ArtifactRefusedError, match="four parameters"):
        build_artifact(result)


def test_summary_only_condition_is_refused() -> None:
    """A timing condition published without its full distribution is refused (⑥)."""
    result = _make_result()
    result.conditions[3].histogram = None  # a timing condition with its distribution stripped
    with pytest.raises(ArtifactRefusedError, match="full histograms|distribution"):
        build_artifact(result)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
