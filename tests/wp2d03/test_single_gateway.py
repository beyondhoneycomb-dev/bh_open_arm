"""Acceptance V — the bypass path passes the single gateway (I-4), proved statically.

Freedrive releases the position path's tau-zero constraint, but it must reach the bus only
through the one enforcement gateway. This is an absence check (no reach for the CAN handle, no
torque cut) plus a presence check (the command path references the gateway), so it is static: a
runtime test could only show the paths it ran. The producer's fail-closed behaviour — when the
gateway holds the command, no motion is emitted — is checked at runtime as the complement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.actuation.staticcheck import find_disable_torque, find_producer_can_access
from backend.freedrive.staticcheck import (
    references_single_gateway,
    scan_freedrive_single_gateway,
)

_FREEDRIVE_TREE = Path("backend/freedrive")


def test_no_reach_for_the_can_handle() -> None:
    assert find_producer_can_access(_FREEDRIVE_TREE) == []


def test_no_torque_cut_in_the_tree() -> None:
    assert find_disable_torque(_FREEDRIVE_TREE) == []


def test_command_path_references_the_single_gateway() -> None:
    assert references_single_gateway(_FREEDRIVE_TREE) is True


def test_combined_single_gateway_scan_is_clean() -> None:
    assert scan_freedrive_single_gateway(_FREEDRIVE_TREE) == []


def test_scan_bites_on_a_direct_bus_reach(tmp_path: Path) -> None:
    # A fixture that reaches for the CAN handle and skips the gateway must be flagged, proving the
    # scan is not vacuous.
    offender = tmp_path / "bypass.py"
    offender.write_text(
        "from backend.actuation.can_writer import CanWriter\n"
        "def drive(writer: CanWriter) -> None:\n"
        "    writer.mit_control_batch(())\n",
        encoding="utf-8",
    )
    violations = scan_freedrive_single_gateway(tmp_path)
    assert violations
    assert not references_single_gateway(tmp_path)


def test_producer_holds_when_the_gateway_blocks() -> None:
    # Fail-closed complement to the static proof: when the gateway rejects (a latched collision
    # guard), the producer emits no motion rather than driving the bus around the gateway.
    pytest.importorskip("mujoco")
    from backend.actuation.clock import WallClock
    from backend.actuation.enforcement import ActuationGateway
    from backend.actuation.guard import CollisionGuard, GuardSample
    from backend.actuation.safety import SafetyFilter
    from backend.freedrive.constants import (
        DEFAULT_KD_FREEDRIVE,
        FREEDRIVE_CONTROL_PERIOD_SEC,
        FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )
    from backend.freedrive.producer import FreedriveProducer
    from tests.wp2d03._support import (
        ENTRY_POSE_RAD,
        ENTRY_VELOCITY_RAD_S,
        arm_safety_limits,
        friction_seed,
        gravity_backend,
    )

    reasons = []
    guard = CollisionGuard(on_latch=reasons.append, clock=WallClock())
    # Latch the guard through repeated fail-closed polls (a missing observation).
    for _ in range(3):
        guard.poll(GuardSample(False, True, True, False))
    assert guard.is_latched is True

    gateway = ActuationGateway(
        safety_filter=SafetyFilter(arm_safety_limits()),
        guard=guard,
        dt_sec=FREEDRIVE_CONTROL_PERIOD_SEC,
        freshness_window_sec=FREEDRIVE_FRESHNESS_WINDOW_SEC,
    )
    producer = FreedriveProducer(
        gravity_backend(),
        friction_seed(),
        gateway,
        tuple(DEFAULT_KD_FREEDRIVE for _ in ENTRY_POSE_RAD),
    )
    frame = producer.produce_frame(ENTRY_POSE_RAD, ENTRY_VELOCITY_RAD_S)
    assert frame.engaged is False
    assert frame.commands == ()
    assert frame.hold_reason is not None
