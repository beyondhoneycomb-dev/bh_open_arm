"""CG-5-05f — a PG-STOP-001 measurement runs and is shown against the 20 ms reference.

Phase-1 measures the soft-estop WS path (browser input → WS → STOP_HOLD) and shows its
P99 beside the `[unconfirmed]` 20 ms NFR-MAN-002 reference, rendering NO pass/fail. The
authoritative release-to-CAN-stop PG-STOP-001 is deferred (no HW), and the reused
`stop_latency` builder refuses to publish a real number without a trusted clock rather
than inventing one.
"""

from __future__ import annotations

import pytest

from backend.loadtest import LoadRun, measure_soft_estop_path
from backend.loadtest.constants import SOFT_ESTOP_PATH_LABEL
from backend.loadtest.stop_path import deferred_real_stop_latency
from backend.torque_bringup.constants import PG_STOP_001, STOP_LATENCY_TARGET_MS
from backend.torque_bringup.stop_latency import (
    StopLatencyArtifactRefusedError,
    build_stop_latency_artifact,
)


def test_soft_estop_p99_is_measured_and_compared(saturated_run: LoadRun) -> None:
    comparison = measure_soft_estop_path(saturated_run)
    assert comparison.path_label == SOFT_ESTOP_PATH_LABEL
    assert comparison.sample_count > 0
    assert comparison.p99_ms > 0.0
    assert comparison.reference_target_ms_unconfirmed == STOP_LATENCY_TARGET_MS


def test_soft_estop_renders_no_pass_fail(saturated_run: LoadRun) -> None:
    comparison = measure_soft_estop_path(saturated_run)
    assert comparison.is_pass_fail is False
    assert "unconfirmed" in comparison.note


def test_exceeding_the_reference_surfaces_the_spine_branch(saturated_run: LoadRun) -> None:
    # Under camera flood the soft path is expected to exceed the 20 ms reference; when
    # it does, the note carries the SPINE §3 branch advice (guidance, not a verdict).
    comparison = measure_soft_estop_path(saturated_run)
    if comparison.exceeds_reference:
        assert "SPINE §3" in comparison.note


def test_authoritative_pg_stop_001_is_deferred() -> None:
    deferred = deferred_real_stop_latency()
    assert deferred["gate"] == PG_STOP_001
    assert deferred["status"] == "deferred"
    assert deferred["fixture_env_var"]
    assert "forge" in deferred["reason"]


def test_real_stop_latency_refuses_without_clock_provenance() -> None:
    # The deferred path is honest: the real builder refuses a number it cannot trust.
    with pytest.raises(StopLatencyArtifactRefusedError):
        build_stop_latency_artifact(samples_sec=(0.01,), clock_provenance=None)
