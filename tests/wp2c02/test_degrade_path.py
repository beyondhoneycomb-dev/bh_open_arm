"""WP-2C-02 acceptance ②: the verdict retargeted onto the convergence bound (NORM-008).

NORM-008 keeps the rate MEASUREMENT and discards the 1 kHz pass/fail line, so the gate reads the
band's `effective_hz` and its own two thresholds: the convergence floor `K/2`, under which the
residual diverges and detection is invalid (ARCHITECTURE_REOPEN), and the 100 Hz residual-detection
target, under which detection works but overshoots (DEGRADED). The band arithmetic itself — the
pattern-B clamp, the f_max bound, the 1/f latency — is WP-1-06's and is not re-checked here.

The order of the two thresholds is the point of `test_a_diverging_gain_reopens_at_any_rate`: a rate
well above the target is still invalid if the gain is too large for it, so rate alone never decides.
"""

from __future__ import annotations

import pytest

from backend.detection_gate import (
    FORWARD_EULER_STABILITY_BOUND,
    RESIDUAL_DETECTION_TARGET_HZ,
    RESIDUAL_DETECTION_TARGET_PERIOD_S,
    DetectionActivationMode,
    DetectionActivationRefusedError,
    converging_rate_floor_hz,
    measure_and_resolve,
    resolve_activation,
)
from backend.detection_gate.activation import FULL_SPEED_CAP_SCALE
from backend.detection_gate.banner import MILLISECONDS_PER_SECOND, PERCENT_PER_UNIT
from backend.safety_bringup.band import FramePattern, resolve_detection_band
from backend.safety_bringup.constants import DETECTION_LOOP_PATTERN_B_CEILING_HZ

# The display precision `DEGRADED_BANNER_TEMPLATE` renders each number at, restated here rather
# than reached through `degraded_banner_text`: a check routed through the formatter renders the
# same swap as the call site under test and cannot see it.
_BANNER_DELAY_PRECISION = 2
_BANNER_CAP_PRECISION = 1

# NFR-SAF-002 (`12` §3.9): collision detection delay must be within 15 ms. Written here as the
# requirement's own number, not imported, because it is what the gate's target is checked against.
# One loop period is a lower bound on that delay — a residual crossing cannot be seen before the
# next sample — so a rate the gate calls fully ACTIVE, with no cap and no banner, must sample at
# least this often. This is the one figure in the suite that does not move with the gain, which is
# what stops the target and `DEFAULT_OBSERVER_GAIN` being re-derived downward together.
_NFR_SAF_002_MAX_DETECTION_DELAY_S = 0.015


def test_pattern_b_meets_the_target_and_is_active(
    synthetic_pass: str, fmax_deferred, observer_gain: float
) -> None:
    """The 625 Hz CAN-FD clamp clears the 100 Hz target outright, so pattern B is not a degrade.

    Pattern B is the designed CAN-FD fallback and the rate it delivers is above what residual
    detection needs, so a gate that demotes it is enforcing a target no frame pattern can reach.
    """
    activation = measure_and_resolve(synthetic_pass, FramePattern.B, fmax_deferred, observer_gain)
    assert activation.mode is DetectionActivationMode.ACTIVE
    assert activation.effective_hz == DETECTION_LOOP_PATTERN_B_CEILING_HZ
    assert activation.speed_cap_scale == FULL_SPEED_CAP_SCALE
    assert activation.banner_visible is False


def test_pattern_a_full_rate_is_active(
    synthetic_pass: str, fmax_deferred, observer_gain: float
) -> None:
    """Pattern A with no f_max bound clears the target too: full cap, no banner."""
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_deferred, observer_gain)
    assert activation.mode is DetectionActivationMode.ACTIVE
    assert activation.effective_hz >= RESIDUAL_DETECTION_TARGET_HZ
    assert activation.speed_cap_scale == FULL_SPEED_CAP_SCALE
    assert activation.banner_visible is False


def test_a_band_exactly_at_the_target_is_active(
    synthetic_pass: str, fmax_at_target, observer_gain: float
) -> None:
    """A loop landing exactly ON the target is ACTIVE — the target is met at it, not above it.

    This is the boundary NORM-008 settles: 100 Hz is the rate at which residual detection is
    stated to work, so the loop that achieves it has no shortfall to answer for. Demoting it would
    cap jog/teleop speed by a factor of exactly 1.0 and show a delay banner for a loop that is
    running at the published rate.
    """
    activation = measure_and_resolve(synthetic_pass, FramePattern.A, fmax_at_target, observer_gain)
    assert activation.effective_hz == RESIDUAL_DETECTION_TARGET_HZ
    assert activation.mode is DetectionActivationMode.ACTIVE
    assert activation.speed_cap_scale == FULL_SPEED_CAP_SCALE
    assert activation.banner_visible is False


def test_the_target_rate_samples_within_the_detection_delay_ceiling() -> None:
    """The ACTIVE/DEGRADED boundary sits at a rate whose own period clears NFR-SAF-002's 15 ms.

    Every other case here follows the gain, so a target lowered in step with `DEFAULT_OBSERVER_GAIN`
    keeps `K*dt` and every gain-relative case intact — the observer traces are identical and the
    suite cannot tell. The delay ceiling is external to both: at 50 Hz the loop alone takes 20 ms
    to sample, so a verdict calling it ACTIVE claims full-speed jogging over a loop that cannot
    detect within the time NFR-SAF-002 allows.
    """
    assert RESIDUAL_DETECTION_TARGET_PERIOD_S <= _NFR_SAF_002_MAX_DETECTION_DELAY_S


def test_below_target_but_converging_is_degraded(
    synthetic_pass: str, fmax_below_target, rate_below_target: float, observer_gain: float
) -> None:
    """Between the floor and the target detection works but overshoots — degrade, not escalate."""
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_target, observer_gain
    )
    assert activation.mode is DetectionActivationMode.DEGRADED
    assert activation.activation_permitted is True
    assert activation.converges is True
    assert activation.effective_hz == rate_below_target
    assert activation.speed_cap_scale == rate_below_target / RESIDUAL_DETECTION_TARGET_HZ
    assert activation.speed_cap_scale < FULL_SPEED_CAP_SCALE


def test_degraded_shows_the_delay_its_own_rate_implies(
    synthetic_pass: str, fmax_below_target, observer_gain: float
) -> None:
    """The delay a DEGRADED verdict shows is 1/f of the rate it was demoted for (FR-SAF-001b).

    The shortfall and the displayed delay are two readings of one measurement, so they are checked
    against each other rather than each against itself. Exact equality, not a tolerance: both come
    from the same band, and any gap between them means the verdict is reporting a loop it is not
    running — a delay shorter than the real one being the direction that reassures the operator.
    """
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_target, observer_gain
    )
    assert activation.mode is DetectionActivationMode.DEGRADED
    assert activation.effective_hz < RESIDUAL_DETECTION_TARGET_HZ
    assert activation.effective_latency_sec == 1.0 / activation.effective_hz


def test_degraded_banner_renders_this_verdict_s_own_delay_and_cap(
    synthetic_pass: str, fmax_below_target, observer_gain: float
) -> None:
    """The banner's two numbers are the verdict's own, so swapping them at the call site fails.

    The delay and the cap enter the template in different units, so a swap keeps both unit
    suffixes and only the magnitudes move — 725.00 ms for a 13.79 ms loop, a 1.4 % cap for an
    enforced 72.5 %. An assertion on the suffix alone cannot tell those apart; the value can.
    """
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_target, observer_gain
    )
    delay_ms = activation.effective_latency_sec * MILLISECONDS_PER_SECOND
    cap_percent = activation.speed_cap_scale * PERCENT_PER_UNIT
    assert f"{delay_ms:.{_BANNER_DELAY_PRECISION}f} ms" in activation.banner
    assert f"{cap_percent:.{_BANNER_CAP_PRECISION}f}%" in activation.banner


def test_below_the_convergence_floor_is_reopen(
    synthetic_pass: str, fmax_below_convergence_floor, observer_gain: float
) -> None:
    """Under the floor the residual diverges, so this is an escalation and activation is refused."""
    activation = measure_and_resolve(
        synthetic_pass, FramePattern.A, fmax_below_convergence_floor, observer_gain
    )
    assert activation.mode is DetectionActivationMode.ARCHITECTURE_REOPEN
    assert activation.converges is False
    assert activation.effective_hz < converging_rate_floor_hz(observer_gain)
    assert activation.locked is True
    assert activation.activation_permitted is False
    assert activation.speed_cap_scale == FULL_SPEED_CAP_SCALE
    with pytest.raises(DetectionActivationRefusedError):
        activation.assert_can_activate()


def test_a_diverging_gain_reopens_at_any_rate(synthetic_pass: str, fmax_deferred) -> None:
    """A rate far above the target is still invalid when the gain cannot converge at it."""
    band = resolve_detection_band(FramePattern.B, fmax_deferred)
    assert band.effective_hz > RESIDUAL_DETECTION_TARGET_HZ
    diverging_gain = FORWARD_EULER_STABILITY_BOUND / band.effective_latency_sec
    activation = resolve_activation(synthetic_pass, band, diverging_gain)
    assert activation.mode is DetectionActivationMode.ARCHITECTURE_REOPEN
    assert activation.converges is False
    assert activation.locked is True
