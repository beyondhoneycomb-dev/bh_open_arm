"""CG-5-05f — a PG-STOP-001 measurement runs and is shown against the 20 ms reference.

Phase-1 measures the soft-estop WS path (browser input → WS → STOP_HOLD) and shows its
P99 beside the `[unconfirmed]` 20 ms NFR-MAN-002 reference, rendering NO pass/fail. The
authoritative release-to-CAN-stop PG-STOP-001 is deferred (no HW), and the reused
`stop_latency` builder refuses to publish a real number without a trusted clock rather
than inventing one.
"""

from __future__ import annotations

import importlib

import pytest

from backend.loadtest import LoadRun, measure_soft_estop_path
from backend.loadtest.constants import SOFT_ESTOP_PATH_LABEL
from backend.loadtest.stop_path import deferred_real_stop_latency
from backend.torque_bringup.constants import (
    CLOCK_METHOD_CANDUMP_HW_TIMESTAMP,
    CLOCK_METHOD_INDEPENDENT_GPIO_MARKER,
    PG_STOP_001,
    STOP_LATENCY_TARGET_MS,
)
from backend.torque_bringup.stop_latency import (
    ClockProvenance,
    StopLatencyArtifactRefusedError,
    build_stop_latency_artifact,
)

# A plausible clock offset and its uncertainty for a provenance the builder accepts. Only
# the method decides the refusal; these two carry into the artifact unjudged.
_OFFSET_SEC = 1e-4
_UNCERTAINTY_SEC = 1e-6

# One sample, small enough to be a credible stop latency. Its value is never compared.
_SAMPLE_SEC = 0.01


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


def test_the_deferred_hook_resolves_to_the_builder_it_names() -> None:
    # The hook is a dotted string, so nothing but this resolves it: renaming or moving the
    # builder would otherwise leave the deferred gate pointing at a symbol that is gone, and
    # the gate's whole claim is that a real measurement has somewhere to arrive.
    module_path, _, attribute = deferred_real_stop_latency()["reverification_hook"].rpartition(".")
    resolved = getattr(importlib.import_module(module_path), attribute)
    assert resolved is build_stop_latency_artifact


def test_real_stop_latency_refuses_without_clock_provenance() -> None:
    # The deferred path is honest: the real builder refuses a number it cannot trust.
    with pytest.raises(StopLatencyArtifactRefusedError):
        build_stop_latency_artifact(samples_sec=(_SAMPLE_SEC,), clock_provenance=None)


def test_real_stop_latency_refuses_a_candump_hw_timestamp() -> None:
    # The forge this rig would actually produce. candump is the one capture path available
    # here, and its hardware timestamp cannot be correlated to the deadman release, so a
    # latency built from it is two clocks subtracted (03 §5.7.0). Refused by method name,
    # not by the absence of an allowed one.
    forged = ClockProvenance(
        method=CLOCK_METHOD_CANDUMP_HW_TIMESTAMP,
        offset_sec=_OFFSET_SEC,
        uncertainty_sec=_UNCERTAINTY_SEC,
    )
    with pytest.raises(StopLatencyArtifactRefusedError, match="forge"):
        build_stop_latency_artifact(samples_sec=(_SAMPLE_SEC,), clock_provenance=forged)


def test_real_stop_latency_publishes_under_a_trusted_clock() -> None:
    # The refusal is a whitelist and not a builder that never publishes: a provenance 03
    # §5.7.0 does admit produces the artifact.
    artifact = build_stop_latency_artifact(
        samples_sec=(_SAMPLE_SEC,),
        clock_provenance=ClockProvenance(
            method=CLOCK_METHOD_INDEPENDENT_GPIO_MARKER,
            offset_sec=_OFFSET_SEC,
            uncertainty_sec=_UNCERTAINTY_SEC,
        ),
    )
    assert artifact["gate"] == PG_STOP_001
    assert artifact["p99_sec"] == _SAMPLE_SEC
    assert artifact["clock_provenance"]["method"] == CLOCK_METHOD_INDEPENDENT_GPIO_MARKER
