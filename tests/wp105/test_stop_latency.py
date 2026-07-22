"""Acceptance ⑥⑬: PG-STOP-001 needs clockProvenance, and it nails no numeric target.

The offline-testable core of PG-STOP-001 is the refusal: a stop latency with no
clockProvenance, or one built from a candump HW timestamp, is a forge and is not published.
The real P99 samples come from a real release and are deferred. Acceptance ⑬: 20 ms is a
reference, never a pass line.
"""

from __future__ import annotations

import pytest

from backend.torque_bringup import (
    ClockProvenance,
    StopLatencyArtifactRefusedError,
    build_stop_latency_artifact,
)
from backend.torque_bringup.constants import (
    CLOCK_METHOD_CANDUMP_HW_TIMESTAMP,
    CLOCK_METHOD_INDEPENDENT_GPIO_MARKER,
    CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING,
    STOP_LATENCY_TARGET_MS,
)

_VALID_PROVENANCE = ClockProvenance(
    method=CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING, offset_sec=0.0, uncertainty_sec=5e-6
)


def test_missing_clock_provenance_refuses_artifact() -> None:
    # Acceptance ⑥: a stop latency without provenance is unfalsifiable and is refused.
    with pytest.raises(StopLatencyArtifactRefusedError, match="no clockProvenance"):
        build_stop_latency_artifact(samples_sec=(0.01, 0.012), clock_provenance=None)


def test_candump_hw_timestamp_is_rejected_as_forge() -> None:
    # A candump HW timestamp cannot correlate to the release event — it is a forge.
    forged = ClockProvenance(
        method=CLOCK_METHOD_CANDUMP_HW_TIMESTAMP, offset_sec=0.0, uncertainty_sec=5e-6
    )
    with pytest.raises(StopLatencyArtifactRefusedError, match="forge"):
        build_stop_latency_artifact(samples_sec=(0.01,), clock_provenance=forged)


def test_valid_provenance_publishes_p99() -> None:
    # With a valid kernel-clock provenance and real samples, the P99 is published.
    artifact = build_stop_latency_artifact(
        samples_sec=(0.008, 0.010, 0.012, 0.030), clock_provenance=_VALID_PROVENANCE
    )
    assert artifact["p99_sec"] == 0.030
    assert artifact["sample_count"] == 4
    assert artifact["clock_provenance"]["method"] == CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING
    assert artifact["stale_on"] == ["PG-RT-001b:PASS"]


def test_gpio_marker_provenance_accepted() -> None:
    artifact = build_stop_latency_artifact(
        samples_sec=(0.01,),
        clock_provenance=ClockProvenance(
            method=CLOCK_METHOD_INDEPENDENT_GPIO_MARKER, offset_sec=1e-4, uncertainty_sec=1e-6
        ),
    )
    assert artifact["p99_sec"] == 0.01


def test_no_samples_leaves_p99_awaited_not_zero() -> None:
    # Deferred real samples => P99 is None (awaited), never fabricated as a pass.
    artifact = build_stop_latency_artifact(samples_sec=(), clock_provenance=_VALID_PROVENANCE)
    assert artifact["p99_sec"] is None
    assert artifact["sample_count"] == 0


def test_target_is_reference_only_never_a_pass_line() -> None:
    # Acceptance ⑬: 20 ms is recorded as a reference; the artifact renders no pass/fail.
    artifact = build_stop_latency_artifact(
        samples_sec=(0.5,),
        clock_provenance=_VALID_PROVENANCE,  # 500 ms, far over 20 ms
    )
    assert artifact["reference_target_ms_unconfirmed"] == STOP_LATENCY_TARGET_MS
    # A P99 an order of magnitude past the reference still produces an artifact with no
    # pass/fail verdict field — the number is not judged here.
    assert "pass" not in {key.lower() for key in artifact}
    assert "verdict" not in {key.lower() for key in artifact}
    assert artifact["p99_sec"] == 0.5


def test_stop_latency_source_has_no_numeric_pass_threshold() -> None:
    # Static reinforcement of ⑬: the module never compares a latency to a threshold.
    from pathlib import Path

    from backend.torque_bringup import stop_latency

    source = Path(stop_latency.__file__).read_text(encoding="utf-8")
    # No comparison operator is applied to the reference target — it is only recorded.
    assert "STOP_LATENCY_TARGET" in source  # it is imported and recorded
    for forbidden in ("< STOP_LATENCY_TARGET", "> STOP_LATENCY_TARGET", "STOP_LATENCY_TARGET_MS <"):
        assert forbidden not in source
