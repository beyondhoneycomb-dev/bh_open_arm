"""CG-4B-03g — the velocity limit and the jump guard are SEPARATE parameters.

FR-INF-040: `max_relative_target` is the jump guard (a per-step `|dq|` cap), not the
velocity limit (`|dq|/dt`). They are two independent fields and neither substitutes
for the other. FR-INF-039: the velocity limit is `min(user, motor VMAX)`, with VMAX
read from the committed `MOTOR_LIMIT_PARAMS` (DM8009 45, DM4340 8, DM4310 30 rad/s).
"""

from __future__ import annotations

import dataclasses

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.inference.load_preflight import (
    JOINT_MOTORS,
    MotionGuards,
    motor_vmax_rad_s,
    resolve_velocity_limit,
)


def test_guards_expose_two_distinct_parameters() -> None:
    """CG-4B-03g: MotionGuards carries velocity_limit_rad_s and jump_guard separately."""
    field_names = {field.name for field in dataclasses.fields(MotionGuards)}
    assert "velocity_limit_rad_s" in field_names
    assert "jump_guard" in field_names


def test_jump_guard_does_not_set_the_velocity_limit() -> None:
    """Setting the jump guard leaves the velocity limit untouched, and vice versa."""
    velocity = resolve_velocity_limit([10.0] * len(JOINT_MOTORS))
    guards = MotionGuards(velocity_limit_rad_s=velocity, jump_guard=0.1)

    # The jump guard is active but the velocity limit is its own, independent vector.
    assert guards.jump_guard_enabled()
    assert guards.velocity_limit_rad_s == velocity

    # Turning the jump guard off (LeRobot default) does not touch the velocity limit.
    guards_no_jump = MotionGuards(velocity_limit_rad_s=velocity, jump_guard=None)
    assert not guards_no_jump.jump_guard_enabled()
    assert guards_no_jump.velocity_limit_rad_s == velocity


def test_velocity_limit_clamps_to_motor_vmax() -> None:
    """The velocity limit is min(user, VMAX): a user asking for 100 is clamped per motor."""
    resolved = resolve_velocity_limit([100.0] * len(JOINT_MOTORS))

    # Derived per motor family rather than transcribed: the DM4340 figure moved from 8 to a
    # measured 10 when this bench answered `16` §3.1's open "24V/48V VMAX (8 vs 10)" question,
    # and a literal here would have made this assert a transcription rather than the clamp.
    expected = tuple(motor_vmax_rad_s(motor) for motor in JOINT_MOTORS)
    assert resolved == expected


def test_velocity_limit_keeps_user_value_when_below_vmax() -> None:
    """A user limit under VMAX is kept (the clamp does not raise a request)."""
    resolved = resolve_velocity_limit([5.0] * len(JOINT_MOTORS))
    assert resolved == (5.0,) * len(JOINT_MOTORS)


def test_motor_vmax_read_from_table() -> None:
    """VMAX per motor family is the committed MOTOR_LIMIT_PARAMS v_max (FR-INF-039)."""
    assert motor_vmax_rad_s(MotorType.DM8009) == MOTOR_LIMIT_PARAMS[MotorType.DM8009].v_max
    assert motor_vmax_rad_s(MotorType.DM4340) == MOTOR_LIMIT_PARAMS[MotorType.DM4340].v_max
    assert motor_vmax_rad_s(MotorType.DM4310) == MOTOR_LIMIT_PARAMS[MotorType.DM4310].v_max
