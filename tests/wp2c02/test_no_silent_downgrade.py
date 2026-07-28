"""WP-2C-02 acceptance ③: zero paths that silently pass a downgrade, and none that pass a diverge.

02b §3.3 names the defect: showing the effective delay without lowering the jog/teleop speed cap
makes the display an alibi. Two mechanisms close it — the verdict cannot be constructed as a silent
downgrade (`__post_init__`), and it cannot be constructed anywhere but the gate (the static
single-gateway scan).

NORM-008 adds a third thing that must be unrepresentable: a verdict that PERMITS detection over a
loop the gain diverges at. That one is not a downgrade at all — the residual means nothing there —
so it raises `ObserverDivergenceError` rather than `SilentDowngradeError`, and it is checked before
the cap and banner so a well-formed degrade cannot smuggle a diverging loop through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.detection_gate import (
    FORWARD_EULER_STABILITY_BOUND,
    GATE_STATE_PASS,
    RESIDUAL_DETECTION_TARGET_HZ,
    DetectionActivation,
    DetectionActivationMode,
    ObserverDivergenceError,
    SilentDowngradeError,
    assert_no_silent_downgrade,
    measure_and_resolve,
    scan_activation_construction,
)
from backend.detection_gate.activation import (
    FULL_SPEED_CAP_SCALE,
    MIN_SPEED_CAP_SCALE,
    NO_BANNER,
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

# A cap that is lowered enough to be a real downgrade, used where the cap is not what is on trial.
_LOWERED_CAP = 0.5

# A cap ABOVE full speed: not a downgrade at all but a licence to jog faster than the un-degraded
# limit. It clears any test phrased as "the cap is not lowered", so only an equality invariant
# refuses it outside DEGRADED.
_RAISED_CAP = 2.0

# A cap below zero: it multiplies commanded velocity, so this reverses the command rather than
# slowing it. It clears an unbounded "below full speed" test, which is why the degrade guard has
# a floor as well as a ceiling.
_NEGATIVE_CAP = -0.5

# The three per-mode invariants all raise a plain `ValueError`, and `SilentDowngradeError`
# subclasses `ValueError` as well, so the exception type alone does not say which check refused.
# Matching on the message does.
_TARGET_REFUSAL = "residual-detection target"
_FULL_CAP_REFUSAL = "must carry the full speed cap"

# The modes the lowered cap is not available to. Outside DEGRADED the cap check reads only
# `speed_cap_scale`, so one band serves all three.
_NON_DEGRADED_MODES = (
    DetectionActivationMode.DISABLED,
    DetectionActivationMode.ACTIVE,
    DetectionActivationMode.ARCHITECTURE_REOPEN,
)

# The ways a DEGRADED verdict stops carrying its downgrade, as (field, value) writes past the
# frozen dataclass: a cap below the floor, a cap exactly ON it, a cap back at full speed, and no
# banner at all. Both floor entries are needed because the floor is exclusive, so a guard that
# reaches it instead of clearing it still refuses the negative one.
_TAMPERED_DEGRADE_FIELDS = (
    ("speed_cap_scale", _NEGATIVE_CAP),
    ("speed_cap_scale", MIN_SPEED_CAP_SCALE),
    ("speed_cap_scale", FULL_SPEED_CAP_SCALE),
    ("banner", NO_BANNER),
)


def _degraded_band(fmax):
    """A real band below the residual-detection target but still converging, reused from WP-1-06."""
    band = resolve_detection_band(FramePattern.A, fmax)
    assert band.effective_hz < RESIDUAL_DETECTION_TARGET_HZ
    return band


def test_degraded_without_lowered_cap_is_refused(fmax_below_target, observer_gain: float) -> None:
    """A DEGRADED verdict that does not lower the speed cap cannot be constructed (③)."""
    band = _degraded_band(fmax_below_target)
    with pytest.raises(SilentDowngradeError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=degraded_banner_text(band.effective_latency_sec, FULL_SPEED_CAP_SCALE),
            observer_gain=observer_gain,
        )


def test_degraded_without_banner_is_refused(fmax_below_target, observer_gain: float) -> None:
    """A DEGRADED verdict that shows no effective-delay banner cannot be constructed (③)."""
    band = _degraded_band(fmax_below_target)
    with pytest.raises(SilentDowngradeError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_LOWERED_CAP,
            banner=NO_BANNER,
            observer_gain=observer_gain,
        )


def test_degraded_with_a_negative_cap_is_refused(fmax_below_target, observer_gain: float) -> None:
    """A DEGRADED verdict whose cap is below zero cannot be constructed (③).

    The cap is a fraction of full jog/teleop speed, so a negative one does not slow the arm, it
    inverts the command — and it passes an unbounded "below full speed" test, which is exactly the
    shape a degrade guard defaults to. The banner is rendered from the same number, so this state
    would even display its cap: "-50.0 %".
    """
    band = _degraded_band(fmax_below_target)
    with pytest.raises(SilentDowngradeError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_NEGATIVE_CAP,
            banner=degraded_banner_text(band.effective_latency_sec, _NEGATIVE_CAP),
            observer_gain=observer_gain,
        )


def test_degraded_at_a_zero_cap_is_refused(fmax_below_target, observer_gain: float) -> None:
    """A DEGRADED verdict whose cap sits exactly ON the floor cannot be constructed (③).

    The floor is exclusive, and the exclusion is what separates a degrade from a halt: at a cap of
    zero the arm does not move at all, so the operator is shown a lowered speed limit for a state
    that has actually ended motion. `test_degraded_with_a_negative_cap_is_refused` sits below the
    floor, which a guard that merely reaches the floor still refuses, so it cannot see this case.
    """
    band = _degraded_band(fmax_below_target)
    with pytest.raises(SilentDowngradeError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=MIN_SPEED_CAP_SCALE,
            banner=degraded_banner_text(band.effective_latency_sec, MIN_SPEED_CAP_SCALE),
            observer_gain=observer_gain,
        )


def test_degraded_at_the_target_rate_is_refused(fmax_deferred, observer_gain: float) -> None:
    """A DEGRADED verdict over a band that MEETS the target cannot be constructed.

    Nothing else about this verdict is malformed — the cap is lowered and the banner is rendered —
    so the mode is the only lie in it: a loop at the target is not degraded, and accepting the
    label would cap jog/teleop speed on a loop that had no shortfall to answer for.
    """
    band = resolve_detection_band(FramePattern.A, fmax_deferred)
    assert band.effective_hz >= RESIDUAL_DETECTION_TARGET_HZ
    with pytest.raises(ValueError, match=_TARGET_REFUSAL):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_LOWERED_CAP,
            banner=degraded_banner_text(band.effective_latency_sec, _LOWERED_CAP),
            observer_gain=observer_gain,
        )


def test_degraded_exactly_at_the_target_rate_is_refused(
    fmax_at_target, observer_gain: float
) -> None:
    """A DEGRADED verdict over a band landing exactly ON the target is refused.

    `test_degraded_at_the_target_rate_is_refused` runs a band an order of magnitude above the
    target, which any comparison refuses. The equality case is the one NORM-008 rules on, and it
    separates "meets the target" from "beats it": a verdict here caps jog/teleop speed for a
    shortfall of zero.
    """
    band = resolve_detection_band(FramePattern.A, fmax_at_target)
    assert band.effective_hz == RESIDUAL_DETECTION_TARGET_HZ
    with pytest.raises(ValueError, match=_TARGET_REFUSAL):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_LOWERED_CAP,
            banner=degraded_banner_text(band.effective_latency_sec, _LOWERED_CAP),
            observer_gain=observer_gain,
        )


def test_active_below_the_target_rate_is_refused(fmax_below_target, observer_gain: float) -> None:
    """An ACTIVE verdict over a band BELOW the target cannot be constructed.

    This is the silent downgrade approached from the mode instead of the cap: the band converges,
    so the verdict is constructible on every other count, and calling it ACTIVE is what would drop
    both the speed cap and the effective-delay display the shortfall requires.
    """
    band = _degraded_band(fmax_below_target)
    with pytest.raises(ValueError, match=_TARGET_REFUSAL):
        DetectionActivation(
            mode=DetectionActivationMode.ACTIVE,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=NO_BANNER,
            observer_gain=observer_gain,
        )


@pytest.mark.parametrize("mode", _NON_DEGRADED_MODES)
def test_non_degraded_mode_cannot_carry_a_lowered_cap(
    mode: DetectionActivationMode, fmax_deferred, observer_gain: float
) -> None:
    """Only DEGRADED lowers the speed cap; the other three modes are refused if they carry one.

    A lowered cap outside DEGRADED is a downgrade with no mode and no banner to account for it.
    The full-cap construction after the refusal is the control: it shows the mode is constructible
    over this band and the cap is what was refused.
    """
    band = resolve_detection_band(FramePattern.A, fmax_deferred)
    with pytest.raises(ValueError, match=_FULL_CAP_REFUSAL):
        DetectionActivation(
            mode=mode,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_LOWERED_CAP,
            banner=NO_BANNER,
            observer_gain=observer_gain,
        )
    DetectionActivation(
        mode=mode,
        pg_fric_001_status=GATE_STATE_PASS,
        band=band,
        speed_cap_scale=FULL_SPEED_CAP_SCALE,
        banner=NO_BANNER,
        observer_gain=observer_gain,
    )


@pytest.mark.parametrize("mode", _NON_DEGRADED_MODES)
def test_non_degraded_mode_cannot_carry_a_raised_cap(
    mode: DetectionActivationMode, fmax_deferred, observer_gain: float
) -> None:
    """A cap ABOVE full speed is refused outside DEGRADED too — the invariant is equality.

    The three non-degraded modes impose no detection-driven downgrade, and "no downgrade" means
    exactly full speed, not "at least full speed". A cap over 1.0 would scale jog/teleop velocity
    past the un-degraded limit from a gate whose only lever is meant to be a reduction, and
    DISABLED and ARCHITECTURE_REOPEN are states where detection is not running at all.
    """
    band = resolve_detection_band(FramePattern.A, fmax_deferred)
    with pytest.raises(ValueError, match=_FULL_CAP_REFUSAL):
        DetectionActivation(
            mode=mode,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_RAISED_CAP,
            banner=NO_BANNER,
            observer_gain=observer_gain,
        )


def test_active_over_a_diverging_band_is_refused(fmax_deferred) -> None:
    """An ACTIVE verdict over a loop its gain diverges at cannot be constructed (NORM-008)."""
    band = resolve_detection_band(FramePattern.A, fmax_deferred)
    diverging_gain = FORWARD_EULER_STABILITY_BOUND / band.effective_latency_sec
    with pytest.raises(ObserverDivergenceError):
        DetectionActivation(
            mode=DetectionActivationMode.ACTIVE,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=NO_BANNER,
            observer_gain=diverging_gain,
        )


def test_degraded_over_a_diverging_band_is_refused(fmax_below_target) -> None:
    """A well-formed degrade cannot smuggle a diverging loop past the cap and banner checks."""
    band = _degraded_band(fmax_below_target)
    diverging_gain = FORWARD_EULER_STABILITY_BOUND / band.effective_latency_sec
    with pytest.raises(ObserverDivergenceError):
        DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=GATE_STATE_PASS,
            band=band,
            speed_cap_scale=_LOWERED_CAP,
            banner=degraded_banner_text(band.effective_latency_sec, _LOWERED_CAP),
            observer_gain=diverging_gain,
        )


def test_gate_degraded_verdict_passes_the_guard(
    synthetic_pass: str, fmax_below_target, observer_gain: float
) -> None:
    """The gate's own DEGRADED verdict clears `assert_no_silent_downgrade`."""
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_target, observer_gain
    )
    assert activation.mode is DetectionActivationMode.DEGRADED
    assert_no_silent_downgrade(activation)


def test_non_degraded_verdicts_pass_the_guard(
    synthetic_pass: str,
    deferred_status: str,
    fmax_deferred,
    fmax_below_convergence_floor,
    observer_gain: float,
) -> None:
    """ACTIVE, DISABLED, and ARCHITECTURE_REOPEN verdicts carry no downgrade and clear the guard."""
    for activation in (
        measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred, observer_gain),
        measure_and_resolve(deferred_status, FramePattern.A, fmax_deferred, observer_gain),
        measure_and_resolve(
            synthetic_pass, FramePattern.A, fmax_below_convergence_floor, observer_gain
        ),
    ):
        assert_no_silent_downgrade(activation)


@pytest.mark.parametrize("field, tampered", _TAMPERED_DEGRADE_FIELDS)
def test_the_guard_refuses_a_tampered_degrade(
    field: str,
    tampered: object,
    synthetic_pass: str,
    fmax_below_target,
    observer_gain: float,
) -> None:
    """`assert_no_silent_downgrade` refuses the states `__post_init__` refuses, not fewer.

    The guard exists for a consumer holding a verdict it did not build, so its refusal branch has
    to be reachable to be checked at all — and `__post_init__` makes every such verdict
    unconstructible. `object.__setattr__` writes past the frozen dataclass to produce one, which is
    also the only way a real caller could hand the guard a degrade with no downgrade in it.
    """
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_target, observer_gain
    )
    assert activation.mode is DetectionActivationMode.DEGRADED
    object.__setattr__(activation, field, tampered)
    with pytest.raises(SilentDowngradeError):
        assert_no_silent_downgrade(activation)


def test_gate_package_has_single_constructor() -> None:
    """No file in the detection-gate package builds a `DetectionActivation` but the gate itself."""
    sites = scan_activation_construction((GATE_PACKAGE,), GATE_CONSTRUCTOR_DEFINITIONS)
    assert sites == []


def test_no_backend_consumer_bypasses_the_gate() -> None:
    """No package anywhere in `backend/` constructs a `DetectionActivation` outside the gate (③)."""
    sites = scan_activation_construction((BACKEND_ROOT,), GATE_CONSTRUCTOR_DEFINITIONS)
    assert sites == []
