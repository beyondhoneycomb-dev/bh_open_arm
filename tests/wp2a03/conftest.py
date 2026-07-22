"""Shared fixtures for the WP-2A-03 jog-path clamp tests.

A three-joint synthetic envelope with distinct per-joint bounds, built directly from
`SafetyLimits` so the tests stay light — they exercise the jog wiring without pulling
the LeRobot/torque stack. The operational envelope is a strict subset of the
mechanical one on every joint, and the three rate guards are set, so the envelope is
one `SafetyLimits.validate()` accepts.
"""

from __future__ import annotations

import pytest

from backend.actuation.safety import SafetyLimits
from backend.jogclamp import JogClampPath
from contracts.units import Deg, Nm

# Per-joint step-delta jump limits, radians. Distinct across joints so a test can tell
# the cap is applied per joint, not with one shared scalar. Joint 1's 0.2 rad ≈ 11.46°.
STEP_DELTA_LIMIT_RAD = (0.1, 0.2, 0.1)


@pytest.fixture
def limits() -> SafetyLimits:
    """A valid three-joint envelope: operational strictly inside mechanical."""
    return SafetyLimits(
        mechanical_deg=(
            (Deg(-180.0), Deg(180.0)),
            (Deg(-90.0), Deg(90.0)),
            (Deg(-90.0), Deg(90.0)),
        ),
        operational_deg=((Deg(-90.0), Deg(90.0)), (Deg(-45.0), Deg(45.0)), (Deg(-45.0), Deg(45.0))),
        velocity_limit_rad_s=(1.0, 1.0, 1.0),
        accel_limit_rad_s2=(5.0, 5.0, 5.0),
        jerk_limit_rad_s3=(50.0, 50.0, 50.0),
        step_delta_limit_rad=STEP_DELTA_LIMIT_RAD,
        peak_torque_nm=(Nm(10.0), Nm(10.0), Nm(10.0)),
        operational_torque_nm=(Nm(10.0), Nm(10.0), Nm(10.0)),
    )


@pytest.fixture
def seeded_path(limits: SafetyLimits) -> JogClampPath:
    """A jog path seeded at the origin pose, ready to shape its first target."""
    path = JogClampPath(limits)
    path.seed_previous((Deg(0.0), Deg(0.0), Deg(0.0)))
    return path
