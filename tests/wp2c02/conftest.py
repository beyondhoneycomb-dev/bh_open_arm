"""Shared fixtures for the WP-2C-02 detection activation gate acceptance tests.

The friction verdict is supplied as a plain gate-state string, the way `torque_bringup` hands its
gates a manifest field. On this host PG-FRIC-001 is hardware-deferred, so `deferred_status` is the
real not-PASS value the gate sees here; `synthetic_pass` is a hypothetical used only to exercise
the PASS-branch logic, never to assert PG-FRIC-001 actually passed.

`fmax_deferred` mirrors this host's reality: no CAN bound (real-bus, absent) and no Python bound
cleared, so `f_max_hz` is unknown. The other three f_max figures are synthetic Python bounds that
reach branches this host cannot: both frame patterns clear the residual-detection target here, so
DEGRADED and ARCHITECTURE_REOPEN only become reachable once WP-1-04 publishes a measured
`f_max_python` under it. Each is placed by the production floor and target rather than by a
frequency written here, so they follow the gain instead of pinning K = 90.
"""

from __future__ import annotations

import pytest

from backend.detection_gate import (
    RESIDUAL_DETECTION_TARGET_HZ,
    converging_rate_floor_hz,
)
from backend.gmo import GmoModelTerms
from backend.gmo.constants import DEFAULT_OBSERVER_GAIN
from backend.rtbench.fmax import FMax, compute_fmax

# Where the two synthetic bounds sit relative to the production floor/target pair.
_MIDPOINT = 0.5
_UNDER_THE_FLOOR = 0.5


@pytest.fixture(scope="session")
def model_terms() -> GmoModelTerms:
    """The GMO model terms the convergence cases drive the real observer and plant through.

    Session-scoped: it loads the v2 MJCF once and carries mutable mujoco scratch buffers, but the
    suite runs sequentially and every call sets the pose before reading.
    """
    return GmoModelTerms()


@pytest.fixture
def observer_gain() -> float:
    """The residual-loop gain the gate evaluates `K*dt` against (WP-2C-01's NORM-011 default)."""
    return DEFAULT_OBSERVER_GAIN


@pytest.fixture
def deferred_status() -> str:
    """The PG-FRIC-001 gate-state on this host: not PASS, because the gate is hardware-deferred."""
    return "FAIL_BLOCKING"


@pytest.fixture
def synthetic_pass() -> str:
    """A synthetic PG-FRIC-001 PASS, used only to exercise the PASS-branch logic offline."""
    return "PASS"


@pytest.fixture
def fmax_deferred() -> FMax:
    """The f_max with both bounds deferred — `f_max_hz` unknown, as on this host."""
    return compute_fmax(None, None)


@pytest.fixture
def rate_below_target(observer_gain: float) -> float:
    """A loop rate the observer converges at but which misses the residual-detection target."""
    return (converging_rate_floor_hz(observer_gain) + RESIDUAL_DETECTION_TARGET_HZ) * _MIDPOINT


@pytest.fixture
def fmax_below_target(rate_below_target: float) -> FMax:
    """A synthetic f_max bounding the loop into the converging-but-degraded band."""
    return compute_fmax(None, rate_below_target)


@pytest.fixture
def fmax_at_target() -> FMax:
    """A synthetic f_max landing the loop exactly ON the residual-detection target.

    The boundary NORM-008 sits on: `resolve_detection_band` carries this bound through unchanged,
    so the band it yields has `effective_hz == RESIDUAL_DETECTION_TARGET_HZ` with no float slack,
    and the gate's target comparisons are exercised at equality rather than near it.
    """
    return compute_fmax(None, RESIDUAL_DETECTION_TARGET_HZ)


@pytest.fixture
def fmax_below_convergence_floor(observer_gain: float) -> FMax:
    """A synthetic f_max bounding the loop under the floor, where the residual does not converge."""
    return compute_fmax(None, converging_rate_floor_hz(observer_gain) * _UNDER_THE_FLOOR)
