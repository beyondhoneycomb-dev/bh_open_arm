"""Acceptance II — deadman release exits immediately to a Cat-2 hold; no toggle, no auto-hold.

Freedrive activates only by holding, and it decays the instant holding stops: an explicit release
holds now, and a lapsed lease latches on the falling edge so a late heartbeat cannot resume it.
The absence of a toggle or auto-hold implementation is proved statically, not assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mujoco")

from backend.actuation.clock import ManualClock
from backend.deadman.messages import RenewalDecision
from backend.freedrive import (
    FRICTION_PASSED_STATUS,
    FreedriveSession,
    FrictionGate,
    HoldCause,
    TickMode,
    find_toggle_or_autohold,
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


def test_explicit_release_holds_immediately() -> None:
    clock = ManualClock()
    session = _engaged_session(clock)
    assert session.active is True

    exit_hold = session.release(ENTRY_POSE_RAD)

    assert session.active is False
    assert exit_hold.cause is HoldCause.OPERATOR_RELEASE
    assert len(exit_hold.hold_commands) == len(ENTRY_POSE_RAD)


def test_lapsed_lease_latches_on_the_falling_edge() -> None:
    clock = ManualClock()
    session = _engaged_session(clock)
    # Tick while live so the monitor sees the live->expired edge, as a real loop would.
    for _ in range(3):
        clock.advance(0.02)
        session.hold_heartbeat()
        assert session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S).mode is TickMode.FREEDRIVE

    clock.advance(_LEASE_SEC * 5)
    lapsed = session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)

    assert lapsed.mode is TickMode.HOLD
    assert lapsed.exit is not None and lapsed.exit.cause is HoldCause.DEADMAN_TIMEOUT
    assert lapsed.was_active is True
    assert session.latch_active is True


def test_no_auto_resume_after_expiry() -> None:
    clock = ManualClock()
    session = _engaged_session(clock)
    clock.advance(0.02)
    session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)  # a live tick to arm the edge
    clock.advance(_LEASE_SEC * 5)
    session.tick(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)  # latches

    late = session.hold_heartbeat()

    assert late.accepted is False
    assert late.decision is RenewalDecision.REJECTED_LATCHED
    assert session.is_held is False


def test_no_toggle_or_autohold_implementation() -> None:
    assert find_toggle_or_autohold(Path("backend/freedrive")) == []


def test_session_exposes_no_toggle_or_autohold_method() -> None:
    for name in dir(FreedriveSession):
        lowered = name.lower()
        assert "toggle" not in lowered
        assert "autohold" not in lowered
        assert "auto_hold" not in lowered
