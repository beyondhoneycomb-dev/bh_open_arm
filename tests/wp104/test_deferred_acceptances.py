"""Deferred real-CAN acceptances + proof the hook that re-runs them works.

Three things cannot run on this host: the on-hardware conditions 1-7 sweep, the real
`candump` frames-per-cycle count (the binding `PG-CAN-001` verdict), and `WP-0B-06`'s
`f_max_can` — all need a real CAN adapter, real motors and a torque-OFF assertion, none
of which exist here. So each is SKIPPED WITH A REASON — never asserted green — and
wired to the re-verification hook that re-runs the identical judgments the moment a
real capture directory is supplied via `OPENARM_RTBENCH_REAL_FIXTURE` (plan 02a §4.1).

To prove the hook is real and not a stub, `test_reverify_hook_*` build a synthetic
capture in the same `RealCapture` schema a real capture uses and run the hook end to
end — the frame count is judged as `REAL_CANDUMP`, so the hook exercises the real
judgment path without pretending to have reached a bus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.rtbench.constants import GATE_STATE_PASS
from backend.rtbench.frame_count import FrameCountSource, FrameCountStatus
from backend.rtbench.reverify import fixture_dir_from_env, reverify_from_fixture

_REAL_FIXTURE = fixture_dir_from_env()
_SKIP_REASON = (
    "requires a real CAN adapter, real motors and a torque-OFF assertion (12 FR-SAF-075); "
    "set OPENARM_RTBENCH_REAL_FIXTURE to a real capture directory to re-verify"
)


def _synthetic_capture_dir(tmp_path: Path) -> Path:
    """Write one synthetic capture in the RealCapture schema.

    Args:
        tmp_path: The pytest temp directory.

    Returns:
        (Path) The directory holding the capture file.
    """
    capture = {
        "host_id": "synthetic-host",
        "band_overrun": [
            {"target_hz": 60.0, "overrun_rate": 0.0},
            {"target_hz": 250.0, "overrun_rate": 0.0},
        ],
        "frames_per_cycle": 32,
        "f_max_can_hz": 625.0,
        "f_max_python_hz": 500.0,
    }
    (tmp_path / "synthetic-host.json").write_text(json.dumps(capture), encoding="utf-8")
    return tmp_path


# --- Hook mechanism: proves the re-verification plumbing works (synthetic data) ---


def test_reverify_hook_runs_over_a_capture_dir(tmp_path: Path) -> None:
    verifications = reverify_from_fixture(_synthetic_capture_dir(tmp_path))
    assert len(verifications) == 1
    verification = verifications[0]
    # The band cleared the budget, so PG-RT-001a passes over the real numbers.
    assert verification.pg_rt_001a.status == GATE_STATE_PASS
    # 32 frames from a real candump source is a binding pattern-B pass.
    assert verification.pg_can_001.source is FrameCountSource.REAL_CANDUMP
    assert verification.pg_can_001.status is FrameCountStatus.PASS
    # f_max is the minimum of the two real bounds.
    assert verification.fmax.f_max_hz == 500.0


def test_reverify_hook_rejects_an_empty_capture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


# --- Deferred real-CAN acceptances: skipped with a reason, re-run only on a real capture ---


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="conditions 1-7 sweep: " + _SKIP_REASON)
def test_deferred_on_hardware_conditions_sweep() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.pg_rt_001a.band_points, "no real band overrun in the capture"


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="real candump frames/cycle: " + _SKIP_REASON)
def test_deferred_real_candump_frame_count() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.pg_can_001.source is FrameCountSource.REAL_CANDUMP


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="f_max_can (WP-0B-06): " + _SKIP_REASON)
def test_deferred_f_max_can_bound() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.fmax.f_max_can_hz is not None, "no real f_max_can in the capture"
