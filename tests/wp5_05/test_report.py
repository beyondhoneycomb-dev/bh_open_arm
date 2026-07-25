"""The assembled phase-1 report covers all six acceptance items and refuses a fake green.

One artifact answers ①–⑥ on the synthetic load. It renders no overall latency pass/fail,
carries the residual risk, and — the safety property — REFUSES to publish when an
ordering invariant did not hold, rather than emitting a green-looking report.
"""

from __future__ import annotations

import pytest

from backend.loadtest import (
    LoadProfile,
    LoadRun,
    build_load_test_report,
)
from backend.loadtest.harness import ClassResult
from backend.loadtest.report import WP_ID, LoadTestReportRefusedError
from contracts.ws.schema import WsFrameType


def test_report_has_every_acceptance_section(saturated_run: LoadRun) -> None:
    artifact = build_load_test_report(saturated_run).artifact
    assert artifact["wp_id"] == WP_ID
    assert artifact["phase"] == 1
    assert artifact["renders_pass_fail_on_latency"] is False
    for key in (
        "cg_5_05a_roundtrip",
        "cg_5_05b_ordering",
        "cg_5_05c_publish_rate",
        "cg_5_05d_lease_autohold",
        "cg_5_05e_residual_risk",
        "cg_5_05f_stop_path",
        "phase2_real_camera_occupancy",
    ):
        assert key in artifact, f"report missing {key}"


def test_report_records_the_autohold_and_hold_emissions(saturated_run: LoadRun) -> None:
    d = build_load_test_report(saturated_run).artifact["cg_5_05d_lease_autohold"]
    assert d["latched"] is True
    assert d["expired_with_fresh_target_emission"]["is_expected_lease_hold"] is True
    assert d["latched_emission"]["is_expected_safety_hold"] is True


def test_report_marks_phase2_deferred(saturated_run: LoadRun) -> None:
    p2 = build_load_test_report(saturated_run).artifact["phase2_real_camera_occupancy"]
    assert p2["ran"] is False
    assert "deferred" in p2["reason"]


def test_report_refuses_when_ordering_inverted(max_load_profile: LoadProfile) -> None:
    # A run where a protected class was dropped: the report must refuse, not footnote it.
    results = {
        WsFrameType.CAMERA: ClassResult(frame_type=WsFrameType.CAMERA, delivered=1, dropped=50),
        WsFrameType.TELEMETRY: ClassResult(
            frame_type=WsFrameType.TELEMETRY, latencies_sec=[0.01], delivered=1, dropped=5
        ),
        WsFrameType.COMMAND: ClassResult(
            frame_type=WsFrameType.COMMAND, latencies_sec=[0.01], delivered=1, dropped=0
        ),
        WsFrameType.LEASE_RENEW: ClassResult(
            frame_type=WsFrameType.LEASE_RENEW, delivered=1, dropped=0
        ),
    }
    inverted = LoadRun(
        profile=max_load_profile, duration_sec=1.0, results=results, peak_buffered_bytes=0
    )
    with pytest.raises(LoadTestReportRefusedError, match="ordering invariant"):
        build_load_test_report(inverted)
