"""A Freedrive tick reaches the collision guard, and one operator ack clears both latches.

The session keeps a `SafetyLatch` and the gateway keeps the guard's own copy of "latched", and
only the second one gates commands. An ack that cleared the first alone reports released while
every frame still holds on COLLISION_LATCH — a state the operator has no way to read from the
session and no way to leave.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.actuation.clock import ManualClock
from backend.actuation.guard import GuardSample
from backend.freedrive import (
    FRICTION_PASSED_STATUS,
    FreedriveSession,
    FrictionGate,
    HoldCause,
    TickMode,
    friction_gate_status,
)
from tests.wp2d03._support import (
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)

# A tick whose read produced no observation. The residual channel stays False: a hand on the
# arm is itself an external-torque residual (FR-MAN-037), so this path suppresses that trip and
# a sample carrying it would be testing a condition Freedrive is required not to have.
BLIND_SAMPLE = GuardSample(
    observation_present=False,
    bus_read_ok=True,
    lock_acquired=True,
    residual_exceeded=False,
)


def _engaged_session() -> FreedriveSession:
    session = FreedriveSession(
        gravity_backend(),
        friction_seed(),
        arm_safety_limits(),
        FrictionGate(friction_gate_status(FRICTION_PASSED_STATUS)),
        ManualClock(),
    )
    session.hold_heartbeat()
    session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy())
    return session


def test_a_blind_tick_exits_freedrive_to_a_hold() -> None:
    session = _engaged_session()

    tick = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, BLIND_SAMPLE)

    assert tick.mode is TickMode.HOLD
    assert tick.exit is not None
    assert tick.exit.cause is HoldCause.GATEWAY_HOLD
    assert session.latch_active


def test_the_hold_a_blind_tick_produces_still_carries_damping() -> None:
    """The exit is a powered position hold, not a torque drop — this arm has no brake."""
    session = _engaged_session()

    tick = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, BLIND_SAMPLE)

    assert tick.exit is not None
    assert tick.exit.zero_kd_position_commands == 0
    assert min(tick.exit.restored_kd) > 0.0


def test_one_ack_clears_the_guard_too_so_freedrive_can_be_re_entered() -> None:
    session = _engaged_session()
    session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, BLIND_SAMPLE)

    session.acknowledge_latch()
    entry = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy())

    assert entry.engaged
    assert entry.frame is not None
    assert entry.frame.engaged
    tick = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy())
    assert tick.mode is TickMode.FREEDRIVE


def test_a_healthy_stream_of_ticks_never_latches() -> None:
    """The residual channel is False on this path by requirement, so a guided arm keeps going."""
    session = _engaged_session()

    modes = [
        session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S, GuardSample.healthy()).mode
        for _ in range(10)
    ]

    assert modes == [TickMode.FREEDRIVE] * 10
    assert not session.latch_active
