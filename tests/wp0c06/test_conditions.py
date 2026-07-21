"""Conditions 2, 3 and 7 produce their declared shapes without manual intervention (①).

Conditions 1, 4, 5 and 6 are exercised through the interleaved measurement and the
full-harness suite; this covers the pattern-A and full-teleop baselines and the
frame-count model, which publishes a provisional model and defers the real
`PG-CAN-001` verdict to `WP-1-04` rather than fabricating a bus measurement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.harness.conditions import (
    MeasurementConfig,
    condition_2_pattern_a,
    condition_3_full_teleop,
    condition_7_frame_count,
)
from sim.harness.load_profile import LoadProfile

_PROFILE = LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024)
_FAST = MeasurementConfig(target_hz=250.0, tick_count=120, warmup=20)


def test_pattern_a_condition(tmp_path: Path) -> None:
    """Condition 2 is a timing condition recording the 16-frame/cycle model."""
    result = condition_2_pattern_a(_PROFILE, _FAST, str(tmp_path))
    assert result.number == 2
    assert result.is_timing and result.histogram is not None
    assert result.histogram.count == _FAST.tick_count
    assert result.extra["frames_per_cycle_model"] == _FAST.pattern_a_frames_per_cycle


def test_full_teleop_condition(tmp_path: Path) -> None:
    """Condition 3 is a timing condition and runs its synthetic teleop pipeline."""
    result = condition_3_full_teleop(_PROFILE, _FAST, str(tmp_path))
    assert result.number == 3
    assert result.is_timing and result.histogram is not None
    assert result.histogram.count == _FAST.tick_count


def test_frame_count_condition_defers_to_wp_1_04() -> None:
    """Condition 7 publishes a provisional model and defers PG-CAN-001 to WP-1-04."""
    result = condition_7_frame_count(_FAST)
    assert result.number == 7
    assert not result.is_timing
    assert result.extra["frames_per_cycle_model"] == _FAST.frames_per_cycle_model
    assert result.extra["provisional"] is True
    assert result.extra["source"] == "synthetic-model"
    assert result.extra["real_measurement_wp"] == "WP-1-04"
    assert result.extra["canonical_gate"] == "PG-CAN-001"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
