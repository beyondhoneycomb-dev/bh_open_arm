"""Acceptance III — on exit, kd is restored before position stiffness: no kd=0 position command.

A Damiao motor vibrates when position is commanded with kd=0 (spec 04 §2.4). Every Freedrive exit
path — explicit release, deadman timeout, a gateway hold — produces a Cat-2 position hold whose
damping is the restored hold kd (> 0), bundled into the same MIT frame as the position stiffness,
so the forbidden (kp>0, kd=0) state never appears.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.actuation.clock import ManualClock
from backend.actuation.config import MIT_HOLD_KD, MIT_HOLD_KP
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

_LEASE_SEC = 0.1


def _engaged_session(clock: ManualClock) -> FreedriveSession:
    gate = FrictionGate(friction_gate_status(FRICTION_PASSED_STATUS))
    session = FreedriveSession(
        gravity_backend(),
        friction_seed(),
        arm_safety_limits(),
        gate,
        clock,
        lease_duration_sec=_LEASE_SEC,
    )
    session.hold_heartbeat()
    session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    return session


def _assert_kd_restored_hold(exit_hold) -> None:  # noqa: ANN001
    assert exit_hold.zero_kd_position_commands == 0
    for command in exit_hold.hold_commands:
        assert command.kd == MIT_HOLD_KD
        assert command.kd > 0.0
        assert command.kp == MIT_HOLD_KP
        # The hold is position-only: the restored damping is not accompanied by a torque command.
        assert command.tau.value == 0.0
    assert all(gain == MIT_HOLD_KD for gain in exit_hold.restored_kd)


def test_release_exit_restores_kd_before_position() -> None:
    session = _engaged_session(ManualClock())
    _assert_kd_restored_hold(session.release(ENTRY_POSE_RAD))


def test_timeout_exit_restores_kd_before_position() -> None:
    clock = ManualClock()
    session = _engaged_session(clock)
    clock.advance(0.02)
    session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    clock.advance(_LEASE_SEC * 5)
    lapsed = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    assert lapsed.mode is TickMode.HOLD
    assert lapsed.exit is not None and lapsed.exit.cause is HoldCause.DEADMAN_TIMEOUT
    _assert_kd_restored_hold(lapsed.exit)


def test_safety_latch_exit_restores_kd_before_position() -> None:
    # A safety latch (a collision guard drives the same shared latch) exits to a Cat-2 hold; it
    # too must restore kd before position.
    from ops.cancel.scheduler import LatchReason

    clock = ManualClock()
    session = _engaged_session(clock)
    session.engage_safety_latch(
        LatchReason(
            gate_id="collision",
            previous_state="freedrive_active",
            new_state="position_hold",
            latched_at=clock.now(),
        )
    )
    tick = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    assert tick.mode is TickMode.HOLD
    assert tick.exit is not None and tick.exit.cause is HoldCause.SAFETY_LATCH
    _assert_kd_restored_hold(tick.exit)
