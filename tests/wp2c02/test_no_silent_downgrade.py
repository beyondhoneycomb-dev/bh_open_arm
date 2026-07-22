"""WP-2C-02 acceptance ③: zero paths that silently pass a downgrade.

02b §3.3 names the defect: showing the effective delay without lowering the jog/teleop speed cap
makes the display an alibi. Two mechanisms close it — the verdict cannot be constructed as a silent
downgrade (`__post_init__`), and it cannot be constructed anywhere but the gate (the static
single-gateway scan). Together they mean the gate's degrade logic is the only path a DEGRADED state
can come from, and every such state carries both the lowered cap and the shown latency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.detection_gate import (
    DetectionActivation,
    DetectionActivationMode,
    SilentDowngradeError,
    assert_no_silent_downgrade,
    measure_and_resolve,
    scan_activation_construction,
)
from backend.detection_gate.banner import degraded_banner_text
from backend.safety_bringup.band import FramePattern, resolve_detection_band

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PACKAGE = REPO_ROOT / "backend" / "detection_gate"
BACKEND_ROOT = REPO_ROOT / "backend"

# The paths that name the constructor as its definition or as a re-export/checker, not as a
# consumer construction — the exclusions the single-gateway scan must apply.
GATE_CONSTRUCTOR_DEFINITIONS = (
    GATE_PACKAGE / "activation.py",
    GATE_PACKAGE / "staticcheck.py",
    GATE_PACKAGE / "__init__.py",
)


def _degraded_band(fmax):
    """A real degraded, pattern-B-clamped band (625 Hz), reused from WP-1-06."""
    band = resolve_detection_band(FramePattern.B, fmax)
    assert band.degraded and band.clamped
    return band


def test_degraded_without_lowered_cap_is_refused(fmax_deferred) -> None:
    """A DEGRADED verdict that does not lower the speed cap cannot be constructed (③)."""
    band = _degraded_band(fmax_deferred)
    with pytest.raises(SilentDowngradeError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status="PASS",
            band=band,
            speed_cap_scale=1.0,
            banner=degraded_banner_text(band.effective_latency_sec, 1.0),
        )


def test_degraded_without_banner_is_refused(fmax_deferred) -> None:
    """A DEGRADED verdict that shows no effective-delay banner cannot be constructed (③)."""
    band = _degraded_band(fmax_deferred)
    with pytest.raises(SilentDowngradeError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status="PASS",
            band=band,
            speed_cap_scale=0.5,
            banner="",
        )


def test_gate_degraded_verdict_passes_the_guard(synthetic_pass: str, fmax_deferred) -> None:
    """The gate's own DEGRADED verdict clears `assert_no_silent_downgrade`."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.B, fmax_deferred)
    assert activation.mode is DetectionActivationMode.DEGRADED
    assert_no_silent_downgrade(activation)


def test_non_degraded_verdicts_pass_the_guard(
    synthetic_pass: str, deferred_status: str, fmax_deferred, fmax_below_1khz
) -> None:
    """ACTIVE, DISABLED, and ARCHITECTURE_REOPEN verdicts carry no downgrade and clear the guard."""
    for activation in (
        measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred),
        measure_and_resolve(deferred_status, FramePattern.A, fmax_deferred),
        measure_and_resolve(synthetic_pass, FramePattern.A, fmax_below_1khz),
    ):
        assert_no_silent_downgrade(activation)


def test_gate_package_has_single_constructor() -> None:
    """No file in the detection-gate package builds a `DetectionActivation` but the gate itself."""
    sites = scan_activation_construction((GATE_PACKAGE,), GATE_CONSTRUCTOR_DEFINITIONS)
    assert sites == []


def test_no_backend_consumer_bypasses_the_gate() -> None:
    """No package anywhere in `backend/` constructs a `DetectionActivation` outside the gate (③)."""
    sites = scan_activation_construction((BACKEND_ROOT,), GATE_CONSTRUCTOR_DEFINITIONS)
    assert sites == []
