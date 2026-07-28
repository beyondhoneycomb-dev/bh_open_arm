"""WP-2C-02: the mode banners — the operator-facing side of the lock, degrade and escalation.

The DISABLED banner is the always-shown FR-SAF-029/030 detection-disabled notice (02b §3.0); the
DEGRADED banner carries the two numbers the downgrade must make visible (effective delay, speed
cap); the ARCHITECTURE_REOPEN banner carries the four the escalation must (gain, period, their
product, the rate that gain needs); a fully ACTIVE loop shows nothing.

The two formatter cases feed made-up inputs, not production constants, so they test the rendering
and not the gate's choice of numbers — that choice is `test_degrade_path`'s subject.
"""

from __future__ import annotations

from backend.detection_gate import (
    DetectionActivationMode,
    disabled_banner_text,
    measure_and_resolve,
    reopen_banner_text,
)
from backend.detection_gate.banner import degraded_banner_text
from backend.detection_gate.constants import (
    DISABLED_BANNER_HEADLINE,
    REOPEN_BANNER_HEADLINE,
)
from backend.safety_bringup.band import FramePattern

# Formatter inputs chosen for legible output, not drawn from the gate: K = 150 over a 20 ms loop
# gives K*dt = 3.00 (diverging) and a floor of 75.0 Hz.
_SAMPLE_GAIN = 150.0
_SAMPLE_PERIOD_S = 0.02


def test_disabled_banner_is_shown_and_names_the_rule(
    deferred_status: str, fmax_deferred, observer_gain: float
) -> None:
    """A locked verdict shows the detection-disabled banner carrying the FR-SAF-030 headline."""
    activation = measure_and_resolve(deferred_status, FramePattern.A, fmax_deferred, observer_gain)
    assert activation.mode is DetectionActivationMode.DISABLED
    assert activation.banner_visible is True
    assert activation.banner == disabled_banner_text()
    assert DISABLED_BANNER_HEADLINE in activation.banner


def test_active_shows_no_banner(synthetic_pass: str, fmax_deferred, observer_gain: float) -> None:
    """A fully active loop needs no banner — there is nothing to warn about."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred, observer_gain)
    assert activation.mode is DetectionActivationMode.ACTIVE
    assert activation.banner == ""
    assert activation.banner_visible is False


def test_reopen_banner_flags_escalation(
    synthetic_pass: str, fmax_below_convergence_floor, observer_gain: float
) -> None:
    """The reopen verdict shows the escalation banner rendered for its own gain and period."""
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_convergence_floor, observer_gain
    )
    assert activation.mode is DetectionActivationMode.ARCHITECTURE_REOPEN
    assert activation.banner == reopen_banner_text(observer_gain, activation.effective_latency_sec)
    assert REOPEN_BANNER_HEADLINE in activation.banner


def test_reopen_banner_carries_the_convergence_numbers() -> None:
    """The escalation renders the gain, the period in ms, the product, and the required rate."""
    text = reopen_banner_text(_SAMPLE_GAIN, _SAMPLE_PERIOD_S)
    assert "150.0" in text
    assert "20.00 ms" in text
    assert "3.00" in text
    assert "75.0 Hz" in text


def test_degraded_banner_carries_delay_and_cap() -> None:
    """The degraded banner renders the effective delay in ms and the speed cap as a percent."""
    text = degraded_banner_text(effective_latency_sec=0.0016, speed_cap_scale=0.625)
    assert "1.60 ms" in text
    assert "62.5%" in text
