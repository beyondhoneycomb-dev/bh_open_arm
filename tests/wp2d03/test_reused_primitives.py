"""Reuse, not re-implementation: Freedrive stands on the committed primitives, adding no second.

WP-2D-03 reuses the single gravity source (WP-2B-02), the identified friction law (WP-2B-07), the
deadman lease and its expiry-latch (WP-2A-02 on the actuation spine), the single enforcement
gateway (WP-1-03), and imports the built Cartesian jog adapter (WP-2D-01) rather than forking any
of them. These tests pin those identities so a later edit cannot quietly grow a second source.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.actuation.enforcement import ActuationGateway
from backend.deadman import DeadmanController
from backend.freedrive.producer import FreedriveProducer
from backend.freedrive.session import FreedriveSession
from tests.wp2d03._support import (
    ENTRY_POSE_RAD,
    ENTRY_VELOCITY_RAD_S,
    arm_safety_limits,
    friction_seed,
    gravity_backend,
)


def _ignore_latch(reason) -> None:  # noqa: ANN001
    """A no-op latch sink for a gateway a test drives with only healthy poses."""


def test_cartesian_jog_adapter_is_importable() -> None:
    # WP-2D-01 is built; Freedrive shares its offline machinery lineage and it must import.
    import backend.cartesian_jog as jog

    assert hasattr(jog, "build_cartesian_jog")


def test_producer_uses_the_injected_gravity_source() -> None:
    gravity = gravity_backend()
    from backend.actuation.clock import WallClock
    from backend.actuation.guard import CollisionGuard
    from backend.actuation.safety import SafetyFilter
    from backend.freedrive.constants import (
        DEFAULT_KD_FREEDRIVE,
        FREEDRIVE_CONTROL_PERIOD_SEC,
        FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )

    gateway = ActuationGateway(
        safety_filter=SafetyFilter(arm_safety_limits()),
        guard=CollisionGuard(on_latch=_ignore_latch, clock=WallClock()),
        dt_sec=FREEDRIVE_CONTROL_PERIOD_SEC,
        freshness_window_sec=FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )
    producer = FreedriveProducer(
        gravity, friction_seed(), gateway, tuple(DEFAULT_KD_FREEDRIVE for _ in ENTRY_POSE_RAD)
    )
    frame = producer.produce_frame(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    # The frame's gravity term equals the injected backend's tau_grav, not a re-derived one.
    expected = gravity.tau_grav(ENTRY_POSE_RAD)
    assert frame.tau_grav_nm == pytest.approx(tuple(float(v) for v in expected), abs=1e-9)


def test_session_holds_a_reused_deadman_controller() -> None:
    from backend.actuation.clock import ManualClock
    from backend.freedrive import FrictionGate, friction_gate_status

    session = FreedriveSession(
        gravity_backend(),
        friction_seed(),
        arm_safety_limits(),
        FrictionGate(friction_gate_status("not-passed")),
        ManualClock(),
    )
    assert isinstance(session._deadman, DeadmanController)


def test_session_routes_through_the_actuation_gateway_type() -> None:
    from backend.actuation.clock import ManualClock
    from backend.freedrive import FrictionGate, friction_gate_status

    session = FreedriveSession(
        gravity_backend(),
        friction_seed(),
        arm_safety_limits(),
        FrictionGate(friction_gate_status("not-passed")),
        ManualClock(),
    )
    assert isinstance(session._producer._gateway, ActuationGateway)
