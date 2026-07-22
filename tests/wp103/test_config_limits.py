"""Acceptance ⑤ / ⑥ / ⑧ — two-stage clamp, three separate rate guards, Peak-Torque clamp.

The limit envelope is validated at construction, so a self-contradicting set can
never back a filter:

- ⑤ An operational position limit wider than the mechanical URDF limit is refused
  (`03` FR-MOT-032): operational must be a subset of mechanical.
- ⑥ Velocity, acceleration and the step-delta jump guard are three independent
  parameters (`14` FR-OPS-012); a config that leaves one unset — the jump guard
  standing in for a velocity limit — is refused.
- ⑧ A torque clamp is bounded by the physical Peak Torque, not the packet-scale
  T_MAX (`03` FR-MOT-037): an operational torque above the peak is refused.
"""

from __future__ import annotations

import pytest

from backend.actuation import SafetyConfigError, SafetyFilter, SafetyLimits, SafetyReason
from contracts.units import Deg, Nm
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    PEAK_TORQUE_NM,
    build_safety_limits,
)
from tests.wp103.conftest import make_limits


def test_operational_wider_than_mechanical_is_refused() -> None:
    """Operational ±90° over a mechanical ±45° envelope is refused (⑤)."""
    limits = make_limits(mechanical_deg=45.0, operational_deg=90.0)
    with pytest.raises(SafetyConfigError) as caught:
        limits.validate()
    assert caught.value.reason is SafetyReason.OPERATIONAL_NOT_SUBSET


def test_operational_within_mechanical_is_accepted() -> None:
    """A tighter operational envelope inside the mechanical one is accepted (⑤)."""
    limits = make_limits(mechanical_deg=90.0, operational_deg=45.0)
    limits.validate()
    SafetyFilter(limits)


def test_velocity_accel_jump_are_three_separate_parameters() -> None:
    """The three rate guards are distinct fields, not one merged knob (⑥)."""
    limits = make_limits()
    assert limits.velocity_limit_rad_s is not None
    assert limits.accel_limit_rad_s2 is not None
    assert limits.step_delta_limit_rad is not None
    # They are separate attributes; no single field serves all three roles.
    assert {"velocity_limit_rad_s", "accel_limit_rad_s2", "step_delta_limit_rad"} <= set(
        vars(limits)
    )


def test_merged_rate_guard_is_refused() -> None:
    """Leaving the velocity limit unset — the jump guard as a stand-in — is refused (⑥)."""
    merged = SafetyLimits(
        mechanical_deg=((Deg(-90.0), Deg(90.0)),),
        operational_deg=((Deg(-45.0), Deg(45.0)),),
        velocity_limit_rad_s=None,
        accel_limit_rad_s2=(50.0,),
        jerk_limit_rad_s3=(500.0,),
        step_delta_limit_rad=(1.0,),
        peak_torque_nm=(Nm(40.0),),
        operational_torque_nm=(Nm(40.0),),
    )
    with pytest.raises(SafetyConfigError) as caught:
        merged.validate()
    assert caught.value.reason is SafetyReason.MERGED_RATE_GUARD


def test_operational_torque_above_peak_is_refused() -> None:
    """A T_MAX-scale torque bound (54) over a 40 Nm peak is refused (⑧)."""
    limits = make_limits(peak_torque_nm=40.0, operational_torque_nm=54.0)
    with pytest.raises(SafetyConfigError) as caught:
        limits.validate()
    assert caught.value.reason is SafetyReason.TORQUE_EXCEEDS_PEAK


def test_peak_torque_bound_is_accepted() -> None:
    """A torque bound at the physical peak (40) is accepted (⑧)."""
    make_limits(peak_torque_nm=40.0, operational_torque_nm=40.0).validate()


def test_follower_uses_physical_peak_torque_not_t_max() -> None:
    """The follower clamps torque by Peak Torque J1/J2=40, J3/J4=27 (⑧, `03` FR-MOT-037)."""
    assert PEAK_TORQUE_NM[0] == 40.0
    assert PEAK_TORQUE_NM[1] == 40.0
    assert PEAK_TORQUE_NM[2] == 27.0
    assert PEAK_TORQUE_NM[3] == 27.0
    limits = build_safety_limits("left")
    assert [torque.value for torque in limits.peak_torque_nm[:4]] == [40.0, 40.0, 27.0, 27.0]
