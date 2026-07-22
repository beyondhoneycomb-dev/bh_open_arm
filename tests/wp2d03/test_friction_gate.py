"""Acceptance I — with PG-FRIC-001 not passed, path (C) cannot start; only (A)/(B) + the banner.

The not-passed status is the real one this host carries: the friction package stamps
``NOT_PASSED_DEFERRED_TO_HARDWARE`` on its synthetic-log fit, and the gate is fed exactly that,
never a fabricated block. The pass path is exercised too, so the block is proven to be a real
gate that opens on a pass rather than an always-off switch.
"""

from __future__ import annotations

import pytest

from backend.freedrive import (
    FRICTION_PASSED_STATUS,
    GRAVITY_UNCOMPENSATED_BANNER,
    EntryRefusal,
    FreedrivePath,
    FrictionGate,
    FrictionGateStatus,
    friction_gate_status,
)
from backend.friction.constants import PG_FRIC_001_STATUS_DEFERRED
from tests.wp2d03._support import (
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)


def test_host_friction_status_maps_to_not_passed() -> None:
    assert friction_gate_status(PG_FRIC_001_STATUS_DEFERRED) is FrictionGateStatus.NOT_PASSED


def test_not_passed_offers_only_a_and_b_with_banner() -> None:
    gate = FrictionGate(friction_gate_status(PG_FRIC_001_STATUS_DEFERRED))
    assert gate.path_c_available is False
    assert gate.offered_paths() == (
        FreedrivePath.PURE_BACKDRIVE,
        FreedrivePath.LOW_STIFFNESS_IMPEDANCE,
    )
    assert FreedrivePath.GRAVITY_COMPENSATED not in gate.offered_paths()
    assert gate.banner() == GRAVITY_UNCOMPENSATED_BANNER


def test_gate_is_real_a_pass_opens_path_c() -> None:
    gate = FrictionGate(friction_gate_status(FRICTION_PASSED_STATUS))
    assert gate.path_c_available is True
    assert FreedrivePath.GRAVITY_COMPENSATED in gate.offered_paths()
    assert gate.banner() is None


def test_unknown_status_fails_closed_to_not_passed() -> None:
    gate = FrictionGate(friction_gate_status("something-provisional"))
    assert gate.path_c_available is False


def test_session_entry_blocked_when_not_passed() -> None:
    pytest.importorskip("mujoco")
    gate = FrictionGate(friction_gate_status(PG_FRIC_001_STATUS_DEFERRED))
    from backend.actuation.clock import ManualClock
    from backend.freedrive import FreedriveSession

    session = FreedriveSession(
        gravity_backend(), friction_seed(), arm_safety_limits(), gate, ManualClock()
    )
    session.hold_heartbeat()
    entry = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)

    assert entry.engaged is False
    assert entry.refusal is EntryRefusal.FRICTION_GATE_BLOCKED
    assert entry.banner == GRAVITY_UNCOMPENSATED_BANNER
    assert FreedrivePath.GRAVITY_COMPENSATED not in entry.offered_paths
    assert entry.frame is None
