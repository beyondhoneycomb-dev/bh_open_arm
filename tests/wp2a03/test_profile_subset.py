"""Acceptance ①: an operational envelope not inside the mechanical one is refused.

The refusal is Wave-1's `SafetyLimits.validate()` (the operational-subset and
rate-guard-separation checks), reused at `JogClampPath` construction. These tests
prove the jog path inherits that refusal rather than carrying a second, drifting copy
of the subset rule: a profile whose operational envelope escapes the mechanical one,
or whose step-delta guard is unset, cannot be turned into a jog path at all.
"""

from __future__ import annotations

import pytest

from backend.actuation.safety import SafetyConfigError, SafetyLimits, SafetyReason
from backend.jogclamp import JogClampPath
from contracts.units import Deg, Nm


def _limits(
    mechanical: tuple[tuple[Deg, Deg], ...],
    operational: tuple[tuple[Deg, Deg], ...],
    step_delta_limit_rad: tuple[float, ...] | None,
) -> SafetyLimits:
    """Build a one- or two-joint envelope varying only the fields under test."""
    width = len(mechanical)
    return SafetyLimits(
        mechanical_deg=mechanical,
        operational_deg=operational,
        velocity_limit_rad_s=tuple(1.0 for _ in range(width)),
        accel_limit_rad_s2=tuple(5.0 for _ in range(width)),
        jerk_limit_rad_s3=tuple(50.0 for _ in range(width)),
        step_delta_limit_rad=step_delta_limit_rad,
        peak_torque_nm=tuple(Nm(10.0) for _ in range(width)),
        operational_torque_nm=tuple(Nm(10.0) for _ in range(width)),
    )


def test_operational_wider_than_mechanical_refuses_construction() -> None:
    """An operational high beyond the mechanical high blocks the jog path."""
    bad = _limits(
        mechanical=((Deg(-90.0), Deg(90.0)),),
        operational=((Deg(-90.0), Deg(95.0)),),
        step_delta_limit_rad=(0.1,),
    )
    with pytest.raises(SafetyConfigError) as caught:
        JogClampPath(bad)
    assert caught.value.reason is SafetyReason.OPERATIONAL_NOT_SUBSET


def test_operational_below_mechanical_low_refuses_construction() -> None:
    """An operational low beneath the mechanical low is equally refused."""
    bad = _limits(
        mechanical=((Deg(-90.0), Deg(90.0)),),
        operational=((Deg(-95.0), Deg(90.0)),),
        step_delta_limit_rad=(0.1,),
    )
    with pytest.raises(SafetyConfigError) as caught:
        JogClampPath(bad)
    assert caught.value.reason is SafetyReason.OPERATIONAL_NOT_SUBSET


def test_unset_step_delta_guard_refuses_construction() -> None:
    """A missing step-delta jump guard is refused (the jump guard is not velocity)."""
    bad = _limits(
        mechanical=((Deg(-90.0), Deg(90.0)),),
        operational=((Deg(-45.0), Deg(45.0)),),
        step_delta_limit_rad=None,
    )
    with pytest.raises(SafetyConfigError) as caught:
        JogClampPath(bad)
    assert caught.value.reason is SafetyReason.MERGED_RATE_GUARD


def test_operational_equal_to_mechanical_is_accepted() -> None:
    """Equality is containment: an operational envelope equal to mechanical is valid."""
    ok = _limits(
        mechanical=((Deg(-90.0), Deg(90.0)),),
        operational=((Deg(-90.0), Deg(90.0)),),
        step_delta_limit_rad=(0.1,),
    )
    path = JogClampPath(ok)
    assert path.limits.width == 1
