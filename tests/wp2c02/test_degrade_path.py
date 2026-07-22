"""WP-2C-02 acceptance ②: a measured 1 kHz miss demotes to DEGRADED with the effective delay shown.

FR-SAF-001b: when the detection loop cannot hold 1 kHz it is demoted, its effective ≈1/f delay is
shown, and — under the pattern-B CAN-FD budget — it is clamped to 625 Hz and accepted. A shortfall
on pattern A (the 1 kHz-capable pattern) is not accepted: no frame pattern reaches 1 kHz, so the
verdict is the architecture-reopen escalation, not a degrade. The band math is reused from WP-1-06,
so these tests check the gate's mapping onto it, not the clamp arithmetic itself.
"""

from __future__ import annotations

from backend.detection_gate import DetectionActivationMode, measure_and_resolve
from backend.safety_bringup.band import FramePattern
from backend.safety_bringup.constants import (
    DETECTION_LOOP_PATTERN_B_CEILING_HZ,
    DETECTION_LOOP_TARGET_HZ,
)

PATTERN_B_SPEED_CAP = DETECTION_LOOP_PATTERN_B_CEILING_HZ / DETECTION_LOOP_TARGET_HZ


def test_pattern_b_demotes_to_degraded_accepted(synthetic_pass: str, fmax_deferred) -> None:
    """Pattern B clamps to 625 Hz and the gate accepts it as DEGRADED (the designed fallback)."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.B, fmax_deferred)
    assert activation.mode is DetectionActivationMode.DEGRADED
    assert activation.activation_permitted is True
    assert activation.effective_hz == DETECTION_LOOP_PATTERN_B_CEILING_HZ


def test_degraded_shows_effective_delay(synthetic_pass: str, fmax_deferred) -> None:
    """The DEGRADED verdict carries the ≈1/f effective delay and shows it in the banner."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.B, fmax_deferred)
    assert activation.effective_latency_sec == 1.0 / DETECTION_LOOP_PATTERN_B_CEILING_HZ
    assert activation.banner_visible is True
    assert "ms" in activation.banner


def test_degraded_lowers_speed_cap(synthetic_pass: str, fmax_deferred) -> None:
    """The DEGRADED verdict lowers the jog/teleop speed cap in proportion to the rate shortfall."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.B, fmax_deferred)
    assert activation.speed_cap_scale == PATTERN_B_SPEED_CAP
    assert activation.speed_cap_scale < 1.0


def test_pattern_a_full_rate_is_active(synthetic_pass: str, fmax_deferred) -> None:
    """Pattern A with no f_max bound holds 1 kHz: not degraded, full speed cap, no banner."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred)
    assert activation.mode is DetectionActivationMode.ACTIVE
    assert activation.effective_hz == DETECTION_LOOP_TARGET_HZ
    assert activation.speed_cap_scale == 1.0
    assert activation.banner_visible is False


def test_pattern_a_below_target_is_architecture_reopen(
    synthetic_pass: str, fmax_below_1khz
) -> None:
    """A 1 kHz miss on pattern A means no pattern reaches it — reopen, not a degrade."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_below_1khz)
    assert activation.mode is DetectionActivationMode.ARCHITECTURE_REOPEN
    assert activation.locked is True
    assert activation.activation_permitted is False
    assert activation.speed_cap_scale == 1.0
