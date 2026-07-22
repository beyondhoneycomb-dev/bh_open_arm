"""Shared fixtures for the WP-2C-02 detection activation gate acceptance tests.

The friction verdict is supplied as a plain gate-state string, the way `torque_bringup` hands its
gates a manifest field. On this host PG-FRIC-001 is hardware-deferred, so `deferred_status` is the
real not-PASS value the gate sees here; `synthetic_pass` is a hypothetical used only to exercise
the PASS-branch logic, never to assert PG-FRIC-001 actually passed.

The f_max figures mirror this host's reality: `fmax_deferred` has no CAN bound (real-bus, absent)
and no Python bound cleared, so `f_max_hz` is unknown; `fmax_below_1khz` is a synthetic Python
bound under the 1 kHz target, used to reach the architecture-reopen branch.
"""

from __future__ import annotations

import pytest

from backend.rtbench.fmax import FMax, compute_fmax


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
def fmax_below_1khz() -> FMax:
    """A synthetic f_max whose Python bound sits below the 1 kHz detection target."""
    return compute_fmax(None, 800.0)
