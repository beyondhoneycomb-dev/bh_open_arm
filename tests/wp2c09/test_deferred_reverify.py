"""The hardware-deferred re-verification hook (plan 02a §4.1).

WP-2C-09's on-hardware claims — a real collision at the real loop rate dumping a
lossless window, and a real payload/thermal drift shrinking the margin — need bytes
this host cannot produce. `test_real_hardware_reverify` skips with a reason until
`OPENARM_EVENTRING_REAL_FIXTURE` points at real captures. The machinery is not
deferred: the tmp-fixture tests drive `reverify_from_fixture` over real-format
captures, proving it re-runs the ring-and-monitor pipeline and compares the verdict,
rather than being a stub. Called with no fixture at all, it raises rather than passing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.event_ring import (
    CHANNEL_COUNT,
    EVENT_JOINT_COUNT,
    HardwareDeferredError,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.event_ring.constants import ARM_JOINT_COUNT
from backend.event_ring.reverify import reverify_capture

_RATE_HZ = 100
_DT = 1.0 / _RATE_HZ
_PRE_SEC = 0.5
_POST_SEC = 0.5
_EVENT_AT = 0.8
_BASELINE_AFTER = 60
_WINDOW = 30
_COMMITTED_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_event.json"


def _row(residual_nm: float) -> list[float]:
    """One joint's channel row with the R column set; every column present."""
    values = [0.0] * CHANNEL_COUNT
    values[4] = residual_nm  # EventChannel.R.column
    return values


def _stream(residual_of_tick: Any) -> list[dict[str, Any]]:
    """A telemetry stream running to just past the post window, residual set per tick."""
    last_tick = round((_EVENT_AT + _POST_SEC) / _DT) + 1
    stream = []
    for tick in range(last_tick + 1):
        residual = residual_of_tick(tick)
        rows = [_row(residual) for _joint in range(EVENT_JOINT_COUNT)]
        stream.append({"at": tick * _DT, "rows": rows})
    return stream


def _capture(*, lossless: bool, reidentify: bool, capacity: int) -> dict[str, Any]:
    """A real-format capture: healthy prefix, then a drift that should shrink the margin."""

    def residual_of_tick(tick: int) -> float:
        return 0.1 if tick < _BASELINE_AFTER else (1.5 if reidentify else 0.1)

    return {
        "name": f"lossless={lossless}_reidentify={reidentify}",
        "capacity": capacity,
        "pre_event_sec": _PRE_SEC,
        "post_event_sec": _POST_SEC,
        "event_at": _EVENT_AT,
        "stream": _stream(residual_of_tick),
        "monitor": {
            "joint_indices": list(range(ARM_JOINT_COUNT)),
            "thresholds_nm": {str(index): 4.0 for index in range(ARM_JOINT_COUNT)},
            "window_len": _WINDOW,
            "margin_decrease_tolerance_nm": 0.2,
            "baseline_after": _BASELINE_AFTER,
        },
        "expect": {"lossless": lossless, "reidentify": reidentify},
    }


def _write(directory: Path, capture: dict[str, Any]) -> None:
    """Write a capture as a JSON file the hook will discover."""
    (directory / f"{capture['name']}.json").write_text(json.dumps(capture), encoding="utf-8")


def test_hook_confirms_a_lossless_reidentifying_capture(tmp_path: Path) -> None:
    """A well-sized capture with real drift replays to lossless + re-identify, as declared."""
    _write(tmp_path, _capture(lossless=True, reidentify=True, capacity=100))

    results = reverify_from_fixture(tmp_path)

    assert len(results) == 1
    assert results[0].matched, results[0].detail


def test_hook_reports_a_verdict_mismatch(tmp_path: Path) -> None:
    """A capture whose declared expectation disagrees with the replay is reported, not passed."""
    # An undersized ring cannot be lossless, yet the capture declares it is.
    _write(tmp_path, _capture(lossless=True, reidentify=True, capacity=5))

    results = reverify_from_fixture(tmp_path)

    assert results and not results[0].matched


def test_committed_fixture_parses_and_replays() -> None:
    """The committed real-format fixture loads and replays through the hook unchanged."""
    capture = json.loads(_COMMITTED_FIXTURE.read_text(encoding="utf-8"))

    result = reverify_capture(capture)

    assert result.matched, result.detail


def test_missing_fixture_raises_rather_than_passing() -> None:
    """With no fixture the hook raises — a deferred check never reports an unearned green."""
    with pytest.raises(HardwareDeferredError):
        reverify_from_fixture(None)


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real collision capture at the real loop rate; set "
        "OPENARM_EVENTRING_REAL_FIXTURE to a directory of event capture .json files"
    ),
)
def test_real_hardware_reverify() -> None:
    """Re-verify against real hardware captures the moment a fixture directory is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    results = reverify_from_fixture(fixture_dir)
    assert results, "real fixture directory declared no captures"
    for result in results:
        assert result.matched, f"{result.name}: {result.detail}"
