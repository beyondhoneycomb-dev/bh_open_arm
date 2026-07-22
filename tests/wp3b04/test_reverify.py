"""The real-fixture re-verification hook: deferred on hardware, machinery runs here.

The physical sync slop of real RealSense cameras and the hardware-sync 3.3 ms target
need hardware this environment lacks, so the real-device leg is deferred behind
`OPENARM_TIMESYNC_REAL_FIXTURE` and skips. The hook's machinery is not deferred: a
planted fixture directory exercises the reload, recompute and bound comparison here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.camera.constants import NANOSECONDS_PER_MILLISECOND
from backend.sensing.timesync.reverify import (
    EXPECTED_FILE,
    REAL_FIXTURE_ENV,
    SESSION_FILE,
    fixture_dir_from_env,
    reverify_from_fixture,
)

_PERIOD_NS = 33 * NANOSECONDS_PER_MILLISECOND
_FRAMES = 40


def _window(offset_ms: int) -> dict[str, list[int]]:
    base = [i * _PERIOD_NS for i in range(_FRAMES)]
    return {"cam_a": base, "cam_b": [t + offset_ms * NANOSECONDS_PER_MILLISECOND for t in base]}


def _plant(fixture_dir: Path, max_end_q99_ms: float, max_drift_ms: float) -> None:
    (fixture_dir / SESSION_FILE).write_text(
        json.dumps({"start": _window(2), "end": _window(5)}), encoding="utf-8"
    )
    (fixture_dir / EXPECTED_FILE).write_text(
        json.dumps({"max_end_q99_ms": max_end_q99_ms, "max_drift_ms": max_drift_ms}),
        encoding="utf-8",
    )


def test_real_device_leg_is_deferred_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no fixture env, the real-hardware re-verification is skipped, not faked."""
    monkeypatch.delenv(REAL_FIXTURE_ENV, raising=False)
    assert fixture_dir_from_env() is None


def test_planted_fixture_within_bounds_matches(tmp_path: Path) -> None:
    """The hook reloads a capture, recomputes drift, and passes within the bound."""
    _plant(tmp_path, max_end_q99_ms=6.0, max_drift_ms=4.0)
    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    assert results[0].pair == ("cam_a", "cam_b")
    assert results[0].matched is True
    assert results[0].report.end_q99_ms == 5.0


def test_planted_fixture_beyond_the_bound_is_flagged(tmp_path: Path) -> None:
    """An end q99 above the recorded bound is reported as a breach, with detail."""
    _plant(tmp_path, max_end_q99_ms=4.0, max_drift_ms=4.0)
    results = reverify_from_fixture(tmp_path)
    assert results[0].matched is False
    assert "end q99" in results[0].detail


def test_fixture_env_points_the_hook_at_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the env is set, the hook resolves the directory it names."""
    monkeypatch.setenv(REAL_FIXTURE_ENV, str(tmp_path))
    assert fixture_dir_from_env() == tmp_path
