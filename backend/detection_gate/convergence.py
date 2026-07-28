"""Whether the residual observer converges at a given gain and detection period (NORM-008).

The observer integrates forward-Euler (`backend/gmo/observer.py:118`,
`self._integral = self._integral + (beta + residual) * dt`), so its residual error obeys
`e[n+1] = (1 - K*dt)*e[n]`. That decays only while `|1 - K*dt| < 1`, i.e. `0 < K*dt < 2` — the one
relation NORM-008 exempts from its "no frequency is a pass/fail gate" ruling, because below it
residual-based detection does not get slower, it stops working: the residual crosses any threshold
every cycle regardless of contact.

This is where the relation lives for the whole tree. WP-2C-03 calls `assert_gain_converges` before
persisting an operator-set gain (an operator who raises K also shortens the period the loop must
hold), and the activation gate calls it when a verdict that permits detection is constructed.
"""

from __future__ import annotations

from backend.detection_gate.constants import FORWARD_EULER_STABILITY_BOUND
from backend.detection_gate.errors import ObserverDivergenceError


def gain_converges(observer_gain: float, detection_dt_s: float) -> bool:
    """Report whether the residual converges at this gain and detection period.

    Total — it never raises, so a caller resolving a verdict can branch on it. Both halves of the
    interval are load-bearing: the upper is the divergence bound, and the lower rejects `K <= 0`,
    which is not a low-pass toward `tau_ext` at all (`backend/gmo/constants.py:36-38` refuses it
    for the same reason), along with a non-physical period.

    Args:
        observer_gain: The residual-loop gain `K`, s^-1.
        detection_dt_s: The detection loop period, s.

    Returns:
        (bool) True when `0 < K*dt < 2`.
    """
    return 0.0 < observer_gain * detection_dt_s < FORWARD_EULER_STABILITY_BOUND


def assert_gain_converges(observer_gain: float, detection_dt_s: float) -> None:
    """Refuse a gain/period pair the residual observer does not converge at.

    Args:
        observer_gain: The residual-loop gain `K`, s^-1.
        detection_dt_s: The detection loop period, s.

    Raises:
        ObserverDivergenceError: When `K*dt` is outside `(0, 2)`.
    """
    if gain_converges(observer_gain, detection_dt_s):
        return
    raise ObserverDivergenceError(
        f"observer gain {observer_gain} over a detection period of {detection_dt_s} s gives "
        f"K*dt = {observer_gain * detection_dt_s}, outside (0, {FORWARD_EULER_STABILITY_BOUND}): "
        "the forward-Euler residual does not converge, so residual-based detection is invalid "
        f"here, not merely slow. That gain needs a loop above "
        f"{converging_rate_floor_hz(observer_gain)} Hz (NORM-008)."
    )


def converging_rate_floor_hz(observer_gain: float) -> float:
    """The loop rate a gain needs to be exceeded by, `K / 2` — 45 Hz at the NORM-011 K = 90.

    Strictly exceeded: at exactly this rate `K*dt` equals the bound and the residual oscillates
    forever instead of settling.

    Args:
        observer_gain: The residual-loop gain `K`, s^-1.

    Returns:
        (float) The rate in Hz below which, and at which, the observer does not converge.
    """
    return observer_gain / FORWARD_EULER_STABILITY_BOUND
