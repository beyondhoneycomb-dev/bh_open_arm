"""RUNS-HERE ④ — an EE over-velocity command is clamped to the ceiling (`FR-TEL-037`).

The per-tick pose delta is bounded in both linear and angular speed: a step within the
ceiling passes unchanged, a step over it is scaled back to exactly the ceiling along
its own direction, so the command still points where the operator moved, only no
faster than allowed. Verified on the limiter directly and through the gate.
"""

from __future__ import annotations

import math

from backend.teleop.safety_gate.pose import IDENTITY_ROTATION, geodesic_angle
from backend.teleop.safety_gate.states import TeleopLinkState
from backend.teleop.safety_gate.velocity import EEVelocityLimiter
from tests.wp3b10.conftest import (
    DT_SEC,
    TICK_NS,
    make_gate,
    make_sample,
    pose_at,
    rotation_z,
)

_DT = 0.1
_MAX_LINEAR = 1.0
_MAX_ANGULAR = 1.57


def test_linear_step_within_ceiling_passes_unchanged() -> None:
    """A slow linear step is admitted verbatim and not flagged."""
    limiter = EEVelocityLimiter(dt_sec=_DT, max_linear_vel_m_s=_MAX_LINEAR)
    result = limiter.limit(pose_at((0.0, 0.0, 0.0)), pose_at((0.05, 0.0, 0.0)))
    assert result.pose.translation == (0.05, 0.0, 0.0)
    assert result.linear_limited is False
    assert result.linear_speed_m_s == 0.5


def test_linear_over_velocity_is_clamped_to_the_ceiling() -> None:
    """A fast linear step is scaled to exactly the ceiling distance along its direction (④)."""
    limiter = EEVelocityLimiter(dt_sec=_DT, max_linear_vel_m_s=_MAX_LINEAR)
    result = limiter.limit(pose_at((0.0, 0.0, 0.0)), pose_at((0.5, 0.0, 0.0)))
    # max step = 1.0 m/s * 0.1 s = 0.1 m, along +x.
    assert result.linear_limited is True
    assert math.isclose(result.pose.translation[0], 0.1, abs_tol=1e-12)
    assert result.pose.translation[1:] == (0.0, 0.0)
    assert result.linear_speed_m_s == 5.0


def test_angular_over_velocity_is_clamped_to_the_ceiling() -> None:
    """A fast rotation step is scaled to the angular ceiling along the same axis (④)."""
    limiter = EEVelocityLimiter(dt_sec=_DT, max_angular_vel_rad_s=_MAX_ANGULAR)
    # A 90° step in one tick is 15.7 rad/s, far over 1.57 rad/s.
    target = pose_at((0.0, 0.0, 0.0), rotation_z(math.pi / 2))
    result = limiter.limit(pose_at((0.0, 0.0, 0.0)), target)
    assert result.angular_limited is True
    max_step = _MAX_ANGULAR * _DT
    reached = geodesic_angle(IDENTITY_ROTATION, result.pose.rotation)
    assert math.isclose(reached, max_step, abs_tol=1e-9)


def test_gate_clamps_a_fast_follow_target() -> None:
    """Through the gate, a large follow jump is limited to the per-tick ceiling (④)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)), max_linear_vel_m_s=_MAX_LINEAR)
    now = 1_000
    gate.step(now, pose_at((0.0, 0.0, 0.0)), sample=make_sample(now))
    gate.notify_alignment_converged(now)
    assert gate.state is TeleopLinkState.FOLLOWING

    now += TICK_NS
    out = gate.step(now, pose_at((0.5, 0.0, 0.0)), sample=make_sample(now))
    assert out.linear_limited is True
    # max step over the 10 ms tick is 1.0 m/s * DT_SEC.
    assert math.isclose(gate.command.translation[0], _MAX_LINEAR * DT_SEC, abs_tol=1e-12)
