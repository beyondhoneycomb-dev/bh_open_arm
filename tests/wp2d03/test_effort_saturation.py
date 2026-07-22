"""Acceptance IV — entry is admitted only after a gravity-torque effort-saturation check.

Path (C) compensates gravity by feeding it forward, which needs actuator effort to spare. If the
gravity term at the entry pose already reaches the headroom fraction of a joint's peak torque,
entry is refused, because compensation would have no room left for friction or a hand-guide. The
peak torque is the same envelope the gateway clamps against.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.actuation.clock import ManualClock
from backend.freedrive import (
    FRICTION_PASSED_STATUS,
    EntryRefusal,
    FreedriveSession,
    FrictionGate,
    friction_gate_status,
)
from backend.freedrive.effort import EffortSaturationCheck
from contracts.units import Nm
from tests.wp2d03._support import (
    ARM_PEAK_TORQUE_NM,
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)


def _session(peak_scale: float) -> FreedriveSession:
    gate = FrictionGate(friction_gate_status(FRICTION_PASSED_STATUS))
    session = FreedriveSession(
        gravity_backend(),
        friction_seed(),
        arm_safety_limits(peak_scale=peak_scale),
        gate,
        ManualClock(),
    )
    session.hold_heartbeat()
    return session


def test_normal_envelope_is_not_saturated() -> None:
    check = EffortSaturationCheck(
        gravity_backend(), tuple(Nm(value) for value in ARM_PEAK_TORQUE_NM)
    )
    verdict = check.check(ENTRY_POSE_RAD)
    assert verdict.saturated is False
    assert not any(verdict.per_joint_saturated)


def test_shrunk_envelope_saturates_and_refuses_entry() -> None:
    session = _session(peak_scale=0.05)
    entry = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    assert entry.engaged is False
    assert entry.refusal is EntryRefusal.EFFORT_SATURATED
    assert entry.effort is not None and entry.effort.saturated is True
    assert any(entry.effort.per_joint_saturated)


def test_normal_envelope_passes_the_effort_gate() -> None:
    session = _session(peak_scale=1.0)
    entry = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    # A held deadman plus an unsaturated pose engages; the effort gate did not block.
    assert entry.effort is not None and entry.effort.saturated is False
    assert entry.engaged is True


def test_headroom_must_be_a_fraction() -> None:
    peak = tuple(Nm(value) for value in ARM_PEAK_TORQUE_NM)
    with pytest.raises(ValueError):
        EffortSaturationCheck(gravity_backend(), peak, headroom=0.0)
    with pytest.raises(ValueError):
        EffortSaturationCheck(gravity_backend(), peak, headroom=1.5)
