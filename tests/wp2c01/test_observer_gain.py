"""WP-2C-01 acceptance ③: the observer gain `K` is settable per joint, independently.

A per-joint gain gives each joint its own first-order residual bandwidth `r_dot = K*(tau_ext - r)`,
so the step response reaches one time constant (63.2% of the injected torque) at `t ~ 1/K`. Driving
the same injection under a per-joint gain vector and reading each joint's rise time back proves the
gains act independently, not as one shared scalar.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.gmo import (
    DEFAULT_OBSERVER_GAIN,
    GmoModelTerms,
    MomentumObserver,
    ObserverConfigError,
    inject_external_force,
)

# One time constant of a first-order step response.
_ONE_TIME_CONSTANT_FRACTION = 0.632
# The measured rise time should sit within this multiplicative band of the predicted `1/K`. The
# discrete forward-Euler response reaches the fraction a little late, so the band is one-sided-ish
# around the prediction rather than tight.
_RISE_TIME_LOWER = 0.6
_RISE_TIME_UPPER = 1.6


def _rise_time_s(model: GmoModelTerms, gain: np.ndarray, joint: int, magnitude_nm: float) -> float:
    """Return the time the joint's residual first reaches one time constant of the injection."""
    observer = MomentumObserver(model, gain=gain)
    injection = inject_external_force(model, joint=joint, magnitude_nm=magnitude_nm, n_steps=800)
    observer.reset(injection.q[0], injection.qdot[0])
    threshold = _ONE_TIME_CONSTANT_FRACTION * magnitude_nm
    for step in range(injection.n_steps):
        residual = observer.update(
            injection.q[step], injection.qdot[step], injection.tau_meas[step], injection.dt
        )
        if abs(residual[joint]) >= threshold:
            return step * injection.dt
    raise AssertionError(f"joint {joint} never reached one time constant")


def test_per_joint_gain_sets_per_joint_bandwidth(model_terms: GmoModelTerms) -> None:
    """Each joint's rise time tracks its own gain, not a shared one (③)."""
    gain = np.array([30.0, 60.0, 90.0, 120.0, 150.0, 180.0, 210.0])
    for joint in range(7):
        measured = _rise_time_s(model_terms, gain, joint=joint, magnitude_nm=4.0)
        predicted = 1.0 / gain[joint]
        assert _RISE_TIME_LOWER * predicted <= measured <= _RISE_TIME_UPPER * predicted


def test_faster_gain_reaches_the_threshold_sooner(model_terms: GmoModelTerms) -> None:
    """On one joint, a higher gain yields a strictly shorter rise time (③)."""
    slow = _rise_time_s(model_terms, np.full(7, 40.0), joint=3, magnitude_nm=4.0)
    fast = _rise_time_s(model_terms, np.full(7, 200.0), joint=3, magnitude_nm=4.0)
    assert fast < slow


def test_scalar_gain_applies_to_every_joint(model_terms: GmoModelTerms) -> None:
    """A scalar gain is broadcast to all seven joints."""
    observer = MomentumObserver(model_terms, gain=DEFAULT_OBSERVER_GAIN)
    assert observer.gain.shape == (7,)
    assert np.allclose(observer.gain, DEFAULT_OBSERVER_GAIN)


def test_non_positive_gain_is_refused(model_terms: GmoModelTerms) -> None:
    """A zero or negative gain entry is refused — the residual loop would not be stable (③)."""
    with pytest.raises(ObserverConfigError):
        MomentumObserver(model_terms, gain=0.0)
    with pytest.raises(ObserverConfigError):
        MomentumObserver(model_terms, gain=[90.0] * 6 + [-1.0])


def test_wrong_width_gain_is_refused(model_terms: GmoModelTerms) -> None:
    """A gain vector that is not seven wide is refused."""
    with pytest.raises(ObserverConfigError):
        MomentumObserver(model_terms, gain=[90.0, 90.0, 90.0])


def test_non_positive_dt_is_refused(model_terms: GmoModelTerms) -> None:
    """A non-positive tick period is refused rather than integrated."""
    observer = MomentumObserver(model_terms, gain=90.0)
    with pytest.raises(ObserverConfigError):
        observer.update([0.0] * 7, [0.0] * 7, [0.0] * 7, dt=0.0)
