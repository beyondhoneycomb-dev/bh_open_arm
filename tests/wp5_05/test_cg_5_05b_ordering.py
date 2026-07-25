"""CG-5-05b — at saturation the camera degrades first, control classes protected.

This is an order, not a number, so it is decidable now. The positive case is the real
saturated run. The negative cases prove the judge is not vacuous: it must return
INVERTED (a FAIL) when a protected class is dropped, and INVERTED when the link never
saturated (no camera shed = no evidence of ordering).
"""

from __future__ import annotations

from backend.loadtest import LoadProfile, LoadRun, judge_ordering
from backend.loadtest.harness import ClassResult
from backend.loadtest.hol_judge import OrderingVerdict
from contracts.ws.schema import WsFrameType


def _run_with(
    profile: LoadProfile,
    *,
    camera_dropped: int,
    telemetry_dropped: int,
    command_dropped: int,
) -> LoadRun:
    """Build a LoadRun with fabricated drop counts to probe the ordering judge."""
    results = {
        WsFrameType.CAMERA: ClassResult(
            frame_type=WsFrameType.CAMERA, delivered=1, dropped=camera_dropped
        ),
        WsFrameType.TELEMETRY: ClassResult(
            frame_type=WsFrameType.TELEMETRY,
            latencies_sec=[0.01],
            delivered=1,
            dropped=telemetry_dropped,
        ),
        WsFrameType.COMMAND: ClassResult(
            frame_type=WsFrameType.COMMAND,
            latencies_sec=[0.01],
            delivered=1,
            dropped=command_dropped,
        ),
        WsFrameType.LEASE_RENEW: ClassResult(
            frame_type=WsFrameType.LEASE_RENEW, delivered=1, dropped=0
        ),
    }
    return LoadRun(profile=profile, duration_sec=1.0, results=results, peak_buffered_bytes=0)


def test_real_saturated_run_is_protected(saturated_run: LoadRun) -> None:
    judgment = judge_ordering(saturated_run)
    assert judgment.verdict is OrderingVerdict.PROTECTED
    assert judgment.camera_dropped > 0
    assert judgment.protected_dropped == 0


def test_control_degrading_first_is_inverted(max_load_profile: LoadProfile) -> None:
    # Camera shed AND a control class dropped: the priority inverted -> FAIL.
    run = _run_with(max_load_profile, camera_dropped=100, telemetry_dropped=0, command_dropped=3)
    judgment = judge_ordering(run)
    assert judgment.verdict is OrderingVerdict.INVERTED
    assert judgment.protected_dropped == 3


def test_no_saturation_is_inverted(max_load_profile: LoadProfile) -> None:
    # Camera never shed: the ordering was not exercised and cannot be claimed.
    run = _run_with(max_load_profile, camera_dropped=0, telemetry_dropped=0, command_dropped=0)
    judgment = judge_ordering(run)
    assert judgment.verdict is OrderingVerdict.INVERTED
    assert "never shed" in judgment.reason
