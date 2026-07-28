"""WP-2C-02 (NORM-008): the forward-Euler convergence bound the detection rate must clear.

The predicate under test is a two-line inequality, so testing it against its own arithmetic would
prove nothing. Every case here drives the REAL `MomentumObserver` through the REAL synthetic plant
(`backend.gmo.synthetic.inject_external_force`) at the rate in question and reads what the residual
actually does, then checks the predicate agrees. The observer trace is the evidence; the predicate
is the claim.

What the traces show at the NORM-011 gain: far below the floor the residual leaves the injected
step by fifty orders of magnitude, at exactly the floor it locks into a two-cycle that crosses any
threshold every other tick, just inside the floor it settles but overshoots to roughly twice the
step, and at the residual-detection target it reaches the step in three ticks with no overshoot.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from backend.detection_gate import (
    FORWARD_EULER_STABILITY_BOUND,
    RESIDUAL_DETECTION_TARGET_HZ,
    RESIDUAL_DETECTION_TARGET_PERIOD_S,
    ObserverDivergenceError,
    assert_gain_converges,
    converging_rate_floor_hz,
    gain_converges,
)
from backend.gmo import GmoModelTerms, MomentumObserver, inject_external_force

# Test signal, not a safety quantity: a step external torque large enough to dominate the plant's
# own excitation, on a joint the trajectory actually moves.
_INJECTED_TORQUE_NM = 5.0
_INJECTION_JOINT = 3

# Long enough for the geometric approach to finish at the slowest converging rate tested
# (|1 - K*dt| = 0.9 there, so 60 steps leaves 0.9^60 of the initial error).
_RUN_STEPS = 60

# The window the settled/oscillating distinction is read over.
_TAIL_STEPS = 10

# Rates expressed as multiples of the convergence floor, so every case follows the gain rather
# than pinning a frequency that is only correct at K = 90.
_WELL_BELOW_FLOOR = 0.25
_INSIDE_BOUND_MARGIN = 0.95
_JUST_ABOVE_FLOOR = 1.01
_JUST_BELOW_FLOOR = 0.99

# A settled residual sits this close to the injected step; an unsettled one is nowhere near it.
_SETTLED_TOL_NM = 0.25
# "No overshoot" means the peak IS the step, to accumulated rounding — a run that overshoots does
# so by whole newton-metres (1.9x the step just inside the bound), so the two never blur.
_NO_OVERSHOOT_TOL_NM = 1.0e-9
# A diverging run leaves the injected step by more than this multiple of it.
_DIVERGENCE_MULTIPLE = 100.0

# What the real observer puts on the struck joint over the first four ticks at the published
# target rate. NORM-008 picks that rate because `K*dt = 0.9` there, so each tick closes 90 % of the
# remaining gap and the trace is `5*(1 - 0.1**n)`; the leading zero is the first update, where the
# observer integral is still at its reset value and the step is not yet visible. Fixed
# newton-metres, not recomputed from the rate — a target that is not 100 Hz renders a different
# trace and has to fail against these.
_TARGET_RATE_SETTLING_TRACE_NM = (0.0, 4.5, 4.95, 4.995)

# Slack for a residual compared against an exact geometric value; the drift over four ticks is
# around 1e-15 Nm.
_GEOMETRIC_TOL_NM = 1.0e-9

# The residual counts as arrived once it is inside this band around the step and stays there. At
# 2 % of the step the target's arriving tick sits at half the band and its nearest four-tick
# neighbour at 1.6x, so the tick count is read with margin on both sides rather than off an edge.
_ARRIVED_TOL_NM = 0.1

# The tick NORM-008's rationale names for the target rate: at `K*dt = 0.9` the residual arrives on
# the third, and both slower and faster loops need more.
_TARGET_SETTLING_TICKS = 3

# Rates probed against that signature, as multiples of the target so the sweep follows the
# constant. Under the target `K*dt` passes 1 and the error changes sign every tick (overshoot);
# over it each tick closes a smaller share of the gap, so arrival takes longer.
_REJECTED_RATE_MULTIPLES = (0.5, 1.25, 2.0, 10.0)


def _residual_trace(
    model: GmoModelTerms, observer_gain: float, rate_hz: float
) -> NDArray[np.float64]:
    """Drive the real observer at one loop rate and return the struck joint's residual per step.

    Args:
        model: The GMO model terms, shared by the observer and the synthetic plant.
        observer_gain: The residual-loop gain `K`.
        rate_hz: The detection loop rate to integrate at.

    Returns:
        (NDArray[np.float64]) The residual on `_INJECTION_JOINT`, one entry per step.
    """
    dt = 1.0 / rate_hz
    observer = MomentumObserver(model, gain=observer_gain)
    injection = inject_external_force(
        model,
        joint=_INJECTION_JOINT,
        magnitude_nm=_INJECTED_TORQUE_NM,
        n_steps=_RUN_STEPS,
        dt=dt,
    )
    observer.reset(injection.q[0], injection.qdot[0])
    trace = [
        observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )[_INJECTION_JOINT]
        for step in range(injection.n_steps)
    ]
    return np.asarray(trace, dtype=np.float64)


def _settling_ticks(trace: NDArray[np.float64], tolerance_nm: float) -> int:
    """The tick on which the residual arrives at the injected step and stays inside the band.

    Every later tick has to stay inside it too: a trace that crosses the step and leaves again has
    not arrived, which is what separates a converging loop from the two-cycle at the bound.

    Args:
        trace: The struck joint's residual, one entry per step.
        tolerance_nm: The band around the injected step, Nm.

    Returns:
        (int) The 1-based tick, or one past the run length when the residual never arrives.
    """
    inside = np.abs(trace - _INJECTED_TORQUE_NM) <= tolerance_nm
    for tick in range(len(trace)):
        if bool(np.all(inside[tick:])):
            return tick + 1
    return len(trace) + 1


def test_target_rate_settling_trace_pins_the_target(
    model_terms: GmoModelTerms, observer_gain: float
) -> None:
    """The target rate's own settling trace in newton-metres — what fixes it at 100 Hz.

    Every other case here follows the gain, so the suite bounds the target into the converging band
    without ever saying where in it the target sits. These four residuals do say: they are what the
    real observer produces at `RESIDUAL_DETECTION_TARGET_HZ` and at no other rate.
    """
    trace = _residual_trace(model_terms, observer_gain, RESIDUAL_DETECTION_TARGET_HZ)
    arrival = trace[: len(_TARGET_RATE_SETTLING_TRACE_NM)]
    assert arrival == pytest.approx(_TARGET_RATE_SETTLING_TRACE_NM, abs=_GEOMETRIC_TOL_NM)
    assert _settling_ticks(trace, _ARRIVED_TOL_NM) == _TARGET_SETTLING_TICKS


@pytest.mark.parametrize("multiple", _REJECTED_RATE_MULTIPLES)
def test_no_other_rate_carries_the_three_tick_signature(
    model_terms: GmoModelTerms, observer_gain: float, multiple: float
) -> None:
    """Arriving on the third tick without overshoot is the target's alone (NORM-008).

    The discriminator NORM-008's rationale names, driven rather than asserted: half the target
    overshoots to nearly twice the step, and 1.25x, twice and ten times it all need more ticks.
    """
    trace = _residual_trace(model_terms, observer_gain, RESIDUAL_DETECTION_TARGET_HZ * multiple)
    overshoots = bool(np.max(trace) > _INJECTED_TORQUE_NM + _NO_OVERSHOOT_TOL_NM)
    ticks = _settling_ticks(trace, _ARRIVED_TOL_NM)
    assert not (ticks == _TARGET_SETTLING_TICKS and not overshoots)


def test_target_period_is_the_target_rate(model_terms: GmoModelTerms, observer_gain: float) -> None:
    """`RESIDUAL_DETECTION_TARGET_PERIOD_S` is the target rate's period, not a second figure.

    A caller that holds a `dt` and one that holds an `f` have to land on the same loop, so the two
    are checked by driving the observer from each and comparing the traces, not by re-dividing.
    """
    assert pytest.approx(1.0) == RESIDUAL_DETECTION_TARGET_PERIOD_S * RESIDUAL_DETECTION_TARGET_HZ
    from_period = _residual_trace(
        model_terms, observer_gain, 1.0 / RESIDUAL_DETECTION_TARGET_PERIOD_S
    )
    from_rate = _residual_trace(model_terms, observer_gain, RESIDUAL_DETECTION_TARGET_HZ)
    assert from_period == pytest.approx(from_rate, abs=_GEOMETRIC_TOL_NM)


def test_well_below_the_floor_diverges_on_the_real_observer(
    model_terms: GmoModelTerms, observer_gain: float
) -> None:
    """A rate far under the floor makes the residual walk away from the injected step (NORM-008)."""
    rate = converging_rate_floor_hz(observer_gain) * _WELL_BELOW_FLOOR
    trace = _residual_trace(model_terms, observer_gain, rate)
    assert np.max(np.abs(trace)) > _DIVERGENCE_MULTIPLE * _INJECTED_TORQUE_NM
    assert gain_converges(observer_gain, 1.0 / rate) is False


def test_target_rate_converges_on_the_real_observer(
    model_terms: GmoModelTerms, observer_gain: float
) -> None:
    """At the residual-detection target the residual reaches the step and stays, no overshoot."""
    trace = _residual_trace(model_terms, observer_gain, RESIDUAL_DETECTION_TARGET_HZ)
    assert trace[-1] == pytest.approx(_INJECTED_TORQUE_NM, abs=_SETTLED_TOL_NM)
    assert np.max(trace) == pytest.approx(_INJECTED_TORQUE_NM, abs=_NO_OVERSHOOT_TOL_NM)
    tail = trace[-_TAIL_STEPS:]
    assert tail.max() - tail.min() < _SETTLED_TOL_NM
    assert gain_converges(observer_gain, RESIDUAL_DETECTION_TARGET_PERIOD_S) is True


def test_exact_floor_never_settles(model_terms: GmoModelTerms, observer_gain: float) -> None:
    """At exactly `K*dt == bound` the residual oscillates forever, so the bound is strict."""
    rate = converging_rate_floor_hz(observer_gain)
    trace = _residual_trace(model_terms, observer_gain, rate)
    tail = trace[-_TAIL_STEPS:]
    assert tail.max() - tail.min() >= _INJECTED_TORQUE_NM
    assert trace[-1] != pytest.approx(_INJECTED_TORQUE_NM, abs=_SETTLED_TOL_NM)
    assert gain_converges(observer_gain, 1.0 / rate) is False


def test_just_inside_the_bound_settles_but_overshoots(
    model_terms: GmoModelTerms, observer_gain: float
) -> None:
    """Between the floor and the target the residual converges — after roughly twice the step.

    This overshoot is why the band is DEGRADED rather than ACTIVE: detection works there, but a
    residual that peaks at ~2x the contact torque will trip a threshold calibrated for the step.
    """
    rate = converging_rate_floor_hz(observer_gain) / _INSIDE_BOUND_MARGIN
    trace = _residual_trace(model_terms, observer_gain, rate)
    assert trace[-1] == pytest.approx(_INJECTED_TORQUE_NM, abs=_SETTLED_TOL_NM)
    assert np.max(trace) > _INJECTED_TORQUE_NM
    assert rate < RESIDUAL_DETECTION_TARGET_HZ
    assert gain_converges(observer_gain, 1.0 / rate) is True


def test_assert_raises_and_names_the_numbers(observer_gain: float) -> None:
    """The refusal carries K, the period, the product and the rate that gain needs."""
    rate = converging_rate_floor_hz(observer_gain) * _WELL_BELOW_FLOOR
    dt = 1.0 / rate
    with pytest.raises(ObserverDivergenceError) as excinfo:
        assert_gain_converges(observer_gain, dt)
    message = str(excinfo.value)
    assert str(observer_gain) in message
    assert str(dt) in message
    assert str(observer_gain * dt) in message
    assert str(FORWARD_EULER_STABILITY_BOUND) in message
    assert str(converging_rate_floor_hz(observer_gain)) in message


def test_assert_returns_at_the_target(observer_gain: float) -> None:
    """The accepted case returns, so the refusal is not refusing everything."""
    assert assert_gain_converges(observer_gain, RESIDUAL_DETECTION_TARGET_PERIOD_S) is None


def test_non_positive_inputs_do_not_converge(observer_gain: float) -> None:
    """A zero/negative gain or period is not a low-pass toward tau_ext at all, so it is refused."""
    assert gain_converges(0.0, RESIDUAL_DETECTION_TARGET_PERIOD_S) is False
    assert gain_converges(-observer_gain, RESIDUAL_DETECTION_TARGET_PERIOD_S) is False
    assert gain_converges(observer_gain, 0.0) is False
    assert gain_converges(observer_gain, -RESIDUAL_DETECTION_TARGET_PERIOD_S) is False
    with pytest.raises(ObserverDivergenceError):
        assert_gain_converges(observer_gain, 0.0)


def test_floor_is_the_rate_where_convergence_flips(observer_gain: float) -> None:
    """The published floor is exactly where the predicate changes answer, probed from both sides."""
    floor = converging_rate_floor_hz(observer_gain)
    assert gain_converges(observer_gain, 1.0 / (floor * _JUST_ABOVE_FLOOR)) is True
    assert gain_converges(observer_gain, 1.0 / (floor * _JUST_BELOW_FLOOR)) is False
    assert gain_converges(observer_gain, 1.0 / floor) is False
