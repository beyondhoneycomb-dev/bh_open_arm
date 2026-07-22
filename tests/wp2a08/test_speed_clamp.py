"""Acceptance (4) — the gripper speed cap is clamped within the DM4310 V_MAX.

The upstream `gripper_posforce_limits[0]=50.0` is a DM3507 figure and is physically
unreachable on a DM4310, so a requested speed above the DM4310 register V_MAX is
clamped to it (`03` FR-MOT-046/049). The ceiling is the CAN register table's value,
not a literal restated here.
"""

from __future__ import annotations

import pytest

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.gripper_endpoint.constants import GRIPPER_SPEED_CAP_RAD_S
from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.posforce import clamp_speed_rad_s, speed_was_clamped
from tests.wp2a08.conftest import make_record

_DM4310_VMAX = MOTOR_LIMIT_PARAMS[MotorType.DM4310].v_max


def test_speed_cap_source_is_the_dm4310_register_vmax() -> None:
    """The cap ceiling is the DM4310 register V_MAX, not a hand-copied constant."""
    assert GRIPPER_SPEED_CAP_RAD_S == _DM4310_VMAX


def test_over_ceiling_request_is_clamped_to_vmax() -> None:
    """A 50 rad/s request clamps down to the DM4310 V_MAX ceiling."""
    assert clamp_speed_rad_s(50.0) == _DM4310_VMAX
    assert speed_was_clamped(50.0)


def test_within_ceiling_request_is_unchanged() -> None:
    """A request already within the ceiling passes through untouched."""
    assert clamp_speed_rad_s(12.0) == 12.0
    assert not speed_was_clamped(12.0)


def test_record_effective_speed_never_exceeds_vmax() -> None:
    """A record built with an over-ceiling request exposes an effective speed <= V_MAX."""
    record = make_record(speed_rad_s=50.0)
    assert record.effective_speed_rad_s == _DM4310_VMAX
    assert record.effective_speed_rad_s <= _DM4310_VMAX


def test_negative_speed_is_refused_not_silently_zeroed() -> None:
    """A negative speed cap is refused rather than clamped into a valid low speed."""
    with pytest.raises(GripperConfigError, match="non-negative"):
        clamp_speed_rad_s(-1.0)
    with pytest.raises(GripperConfigError, match="non-negative"):
        make_record(speed_rad_s=-1.0)
