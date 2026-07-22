"""Acceptance ②: the artifact assembles under a trusted clock and refuses otherwise.

The bench composes the acceptance-③ precondition, the reused WP-1-05 clock-gated total
P99, and the four-stage decomposition. These check that composition: it publishes under a
trusted clock, it inherits WP-1-05's refusal for a missing or forged clock (one source for
that rule), it refuses a stop path that holds `disable_torque`, and it records the 20 ms
target as a labelled reference only — never a pass line (WP-2A-06 acceptance ②).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.rtbench.constants import REQUIRED_STALE_TRIGGER
from backend.stopbench import (
    REFERENCE_TARGET_MS_UNCONFIRMED,
    StopPathSample,
    build_stop_path_regression_artifact,
)
from backend.stopbench.bench import REAL_CAPTURE_BASIS, SYNTHETIC_BASIS
from backend.stopbench.precondition import DisableTorqueOnStopPathError
from backend.torque_bringup import ClockProvenance, StopLatencyArtifactRefusedError
from backend.torque_bringup.constants import CLOCK_METHOD_CANDUMP_HW_TIMESTAMP


def test_artifact_assembles_under_a_trusted_clock(
    synthetic_samples: list[StopPathSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_stop_path_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock
    )
    assert artifact["wp_id"] == "WP-2A-06"
    assert artifact["gate"] == "PG-STOP-001"
    assert artifact["basis"] == SYNTHETIC_BASIS
    assert artifact["no_disable_torque_precondition"]["passed"] is True
    assert artifact["total_latency"]["p99_sec"] is not None
    assert set(artifact["path_decomposition"]["segments"]) == {
        "harness_event",
        "transmit",
        "scheduler",
        "can",
    }
    # The provisional lineage trigger is carried, so a confirmed PG-RT-001b re-derives this.
    assert REQUIRED_STALE_TRIGGER in artifact["stale_on"]


def test_missing_clock_provenance_is_refused(
    synthetic_samples: list[StopPathSample],
) -> None:
    with pytest.raises(StopLatencyArtifactRefusedError):
        build_stop_path_regression_artifact(samples=synthetic_samples, clock_provenance=None)


def test_candump_forge_clock_is_refused(synthetic_samples: list[StopPathSample]) -> None:
    forged = ClockProvenance(
        method=CLOCK_METHOD_CANDUMP_HW_TIMESTAMP, offset_sec=0.0, uncertainty_sec=0.0
    )
    with pytest.raises(StopLatencyArtifactRefusedError):
        build_stop_path_regression_artifact(samples=synthetic_samples, clock_provenance=forged)


def test_disable_torque_on_stop_path_is_refused_before_measuring(
    synthetic_samples: list[StopPathSample], valid_clock: ClockProvenance, tmp_path: Path
) -> None:
    (tmp_path / "cutting_stop.py").write_text(
        "def stop(bus):\n    bus.disable_torque()\n", encoding="utf-8"
    )
    with pytest.raises(DisableTorqueOnStopPathError):
        build_stop_path_regression_artifact(
            samples=synthetic_samples,
            clock_provenance=valid_clock,
            stop_path_root=tmp_path,
        )


def test_target_is_a_reference_never_a_pass_line(
    synthetic_samples: list[StopPathSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_stop_path_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock
    )
    assert artifact["reference_target_ms_unconfirmed"] == REFERENCE_TARGET_MS_UNCONFIRMED
    assert "[unconfirmed]" in artifact["reference_note"]
    # No verdict on the latency: the total-latency evidence carries no pass/fail field.
    total = artifact["total_latency"]
    assert "passed" not in total
    assert "status" not in total


def test_deferred_manifest_names_the_hook_and_awaited_inputs(
    synthetic_samples: list[StopPathSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_stop_path_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock
    )
    deferred = artifact["deferred"]
    assert deferred["reverification_hook"] == "backend.stopbench.reverify.reverify_from_fixture"
    assert deferred["fixture_env_var"] == "OPENARM_STOPBENCH_REAL_FIXTURE"
    assert deferred["awaited_inputs"], "an offline run still awaits the on-rig measurement"


def test_real_capture_basis_awaits_nothing(
    synthetic_samples: list[StopPathSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_stop_path_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock, basis=REAL_CAPTURE_BASIS
    )
    assert artifact["deferred"]["awaited_inputs"] == []


def test_deferred_measurement_publishes_no_p99(valid_clock: ClockProvenance) -> None:
    # With no real samples the tail is awaited, not fabricated as zero.
    artifact = build_stop_path_regression_artifact(samples=[], clock_provenance=valid_clock)
    assert artifact["total_latency"]["p99_sec"] is None
    assert artifact["path_decomposition"]["sample_count"] == 0
