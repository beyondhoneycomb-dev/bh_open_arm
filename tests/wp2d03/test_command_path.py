"""The path-(C) command shape and its routing through the single gateway (FR-MAN-030).

The frame is ``(kp=0, kd=kd_freedrive, q, dq=0, tau=tau_grav+tau_fric)`` per joint, and it is
built from the single gateway's verdict — the gains it validated and the torque it clamped. These
tests pin the shape, the feed-forward composition, the Peak-Torque clamp, and that the producer
is a swappable scheduler producer that holds no CAN handle.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")

from backend.actuation.clock import ManualClock, WallClock
from backend.actuation.mailbox import TargetMailbox
from backend.actuation.producer import MailboxProducer, Producer
from backend.actuation.transition import ModeTransition
from backend.freedrive import (
    FRICTION_PASSED_STATUS,
    FreedriveSession,
    FrictionGate,
    friction_gate_status,
)
from backend.freedrive.constants import DEFAULT_KD_FREEDRIVE, FREEDRIVE_KP
from backend.freedrive.producer import FreedriveProducer
from tests.wp2d03._support import (
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)


def _passed_session(**kwargs) -> FreedriveSession:
    gate = FrictionGate(friction_gate_status(FRICTION_PASSED_STATUS))
    session = FreedriveSession(
        gravity_backend(), friction_seed(), arm_safety_limits(), gate, ManualClock(), **kwargs
    )
    session.hold_heartbeat()
    return session


def test_frame_has_zero_kp_and_freedrive_damping() -> None:
    session = _passed_session()
    entry = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    assert entry.engaged is True
    frame = entry.frame
    assert frame is not None and frame.engaged is True
    assert len(frame.commands) == len(ENTRY_POSE_RAD)
    for command in frame.commands:
        assert command.kp == FREEDRIVE_KP == 0.0
        assert command.kd == DEFAULT_KD_FREEDRIVE
        assert command.dq.value == 0.0


def test_feedforward_is_gravity_plus_friction() -> None:
    session = _passed_session()
    frame = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S).frame
    assert frame is not None
    gravity = gravity_backend().tau_grav(ENTRY_POSE_RAD)
    friction = [
        float(params.tau(np.asarray([speed]))[0])
        for params, speed in zip(friction_seed(), ENTRY_VELOCITY_RAD_S, strict=True)
    ]
    for index, command in enumerate(frame.commands):
        expected = gravity[index] + friction[index]
        assert command.tau.value == pytest.approx(expected, abs=1e-9)
        assert frame.tau_grav_nm[index] == pytest.approx(gravity[index], abs=1e-9)
        assert frame.tau_fric_nm[index] == pytest.approx(friction[index], abs=1e-9)


def test_per_joint_damping_is_honored() -> None:
    kd = (0.1, 0.15, 0.2, 0.25, 0.3, 0.12, 0.18)
    session = _passed_session(kd_freedrive=kd)
    frame = session.enter(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S).frame
    assert frame is not None
    assert tuple(command.kd for command in frame.commands) == kd


def test_torque_is_clamped_to_peak_by_the_gateway() -> None:
    # A tiny peak envelope forces the gateway to clamp the feed-forward torque to Peak Torque,
    # proving the command's tau came through the gateway clamp, not around it.
    limits = arm_safety_limits(peak_scale=0.05)
    producer = FreedriveProducer(
        gravity_backend(),
        friction_seed(),
        _gateway_from_limits(limits),
        tuple(DEFAULT_KD_FREEDRIVE for _ in ENTRY_POSE_RAD),
    )
    frame = producer.produce_frame(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    peak = [value.value for value in limits.peak_torque_nm]
    for index, command in enumerate(frame.commands):
        assert abs(command.tau.value) <= abs(peak[index]) + 1e-9


def test_producer_is_a_scheduler_producer() -> None:
    producer = FreedriveProducer(
        gravity_backend(),
        friction_seed(),
        _gateway_from_limits(arm_safety_limits()),
        tuple(DEFAULT_KD_FREEDRIVE for _ in ENTRY_POSE_RAD),
    )
    typed: Producer = producer  # static conformance to the scheduler Producer surface
    assert typed.producer_id == "freedrive"

    clock = WallClock()
    mailbox = TargetMailbox()
    initial = MailboxProducer("initial", mailbox, clock)
    transition = ModeTransition(initial)
    transition.begin(producer)
    assert transition.in_progress is True
    # The swap commits the Freedrive producer in as the active producer and returns the outgoing.
    assert transition.commit() is initial
    assert transition.active_id == "freedrive"

    producer.join()
    assert producer.joined is True


def _gateway_from_limits(limits):  # noqa: ANN001, ANN202
    from backend.actuation.enforcement import ActuationGateway
    from backend.actuation.guard import CollisionGuard
    from backend.actuation.safety import SafetyFilter
    from backend.freedrive.constants import (
        FREEDRIVE_CONTROL_PERIOD_SEC,
        FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )

    guard = CollisionGuard(on_latch=_ignore_latch, clock=WallClock())
    return ActuationGateway(
        safety_filter=SafetyFilter(limits),
        guard=guard,
        dt_sec=FREEDRIVE_CONTROL_PERIOD_SEC,
        freshness_window_sec=FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )


def _ignore_latch(reason) -> None:  # noqa: ANN001
    """A no-op latch sink for a gateway the test drives with only healthy poses."""
