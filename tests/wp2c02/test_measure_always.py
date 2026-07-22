"""WP-2C-02 acceptance ②: the detection-loop cycle time is always measured, in every mode.

The measurement is a required input to the verdict, not an optional step: `measure_and_resolve`
composes the band resolution with the gate, and `resolve_activation` takes a band by value, so
there is no path to a verdict without one. Even a DISABLED verdict carries the band the loop would
run at, which is what lets the effective delay be shown the moment PG-FRIC-001 passes.
"""

from __future__ import annotations

import pytest

from backend.detection_gate import DetectionActivationMode, measure_and_resolve
from backend.safety_bringup.band import FramePattern

ALL_FRAME_PATTERNS = (FramePattern.A, FramePattern.B)


@pytest.mark.parametrize("frames", ALL_FRAME_PATTERNS)
def test_disabled_verdict_still_carries_a_measured_band(
    deferred_status: str, fmax_deferred, frames: int
) -> None:
    """A locked (DISABLED) verdict still carries the measured band — never skipped."""
    activation = measure_and_resolve(deferred_status, frames, fmax_deferred)
    assert activation.mode is DetectionActivationMode.DISABLED
    assert activation.band is not None
    assert activation.effective_hz > 0.0
    assert activation.band.frames_per_cycle == frames


def test_effective_latency_is_reciprocal_of_rate(synthetic_pass: str, fmax_deferred) -> None:
    """The shown effective delay is exactly 1/effective_hz (the ≈1/f FR-SAF-001b figure)."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.B, fmax_deferred)
    assert activation.effective_latency_sec == pytest.approx(1.0 / activation.effective_hz)


def test_band_provenance_is_carried(synthetic_pass: str, fmax_deferred) -> None:
    """The verdict exposes the band's provisional flag, so a consumer sees a synthetic f_max."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred)
    assert activation.band.provisional is True
