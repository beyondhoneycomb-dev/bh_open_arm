"""The deadman lease latch is superior to link recovery — proven against the real lease.

`test_no_auto_resume` establishes the refusal against a controllable `FakeLease`; this
closes the loop against the object the deadman actually owns. It drives the genuine
`WP-2A-02` `DeadmanController` on the real Wave-1 spine to a latch, hands that
controller to the gate as its `LeaseLatchView`, and shows the gate refuses to enter
ALIGNING while the real latch is held and permits it only once the deadman re-arm
handshake has cleared the latch. Nothing here renews or latches the lease itself — the
gate only reads it — so the deadman keeps its single definition of expiry.
"""

from __future__ import annotations

import pytest

from backend.teleop.safety_gate import deadman_lease_view
from backend.teleop.safety_gate.states import RearmRequiredError, TeleopLinkState
from tests.wp2a02.conftest import DeadmanHarness
from tests.wp3b10.conftest import TICK_NS, make_gate, make_sample, pose_at

_LIVE_TICKS = 15
_EXPIRY_CEILING_TICKS = 200
_LOSS_ADVANCE_NS = 20 * TICK_NS


def _latched_deadman() -> DeadmanHarness:
    """Drive a real deadman to a latched state and return its harness."""
    harness = DeadmanHarness()
    harness.take_deadman()
    for _ in range(_LIVE_TICKS):
        harness.tick(publish=True, renew=True)
    harness.run_until_latched(_EXPIRY_CEILING_TICKS)
    assert harness.controller.latched
    return harness


def test_real_deadman_controller_is_a_lease_latch_view() -> None:
    """The genuine `DeadmanController` satisfies the gate's `LeaseLatchView` structurally."""
    harness = DeadmanHarness()
    harness.take_deadman()
    # It exposes the one member the gate reads; the gate never imports the concrete type.
    assert hasattr(harness.controller, "latched")
    assert harness.controller.latched is False


def test_gate_refuses_reengage_while_real_lease_latched_then_permits_after_rearm() -> None:
    """A held real lease latch blocks ALIGNING; the deadman re-arm is what unblocks it."""
    harness = _latched_deadman()
    # Consume the real deadman lease through the production adapter — the gate reads the
    # same latch WP-2A-02 owns, not a lease of its own.
    gate = make_gate(
        seed_pose=pose_at((0.0, 0.0, 0.0)), lease=deadman_lease_view(harness.controller)
    )

    # Bring the teleop link up, then down, independently of the lease clock.
    now = 1_000
    gate.step(now, pose_at((0.0, 0.0, 0.0)), sample=make_sample(now))
    gate.notify_alignment_converged(now)
    now += _LOSS_ADVANCE_NS
    gate.step(now, pose_at((0.0, 0.0, 0.0)))
    assert gate.state is TeleopLinkState.LINK_LOST

    # The teleop link is healthy again, but the deadman lease is latched: re-engage is
    # refused — the re-arm handshake is the superior gate.
    now += TICK_NS
    gate.step(now, pose_at((0.1, 0.0, 0.0)), sample=make_sample(now))
    with pytest.raises(RearmRequiredError):
        gate.request_reengage(now)
    assert gate.state is TeleopLinkState.LINK_LOST

    # Complete the deadman re-arm handshake; the real latch clears.
    harness.controller.request_rearm()
    harness.controller.confirm_rearm()
    assert harness.controller.latched is False

    # Now the identical re-engage is permitted, and it lands in ALIGNING (never direct).
    gate.request_reengage(now)
    assert gate.state is TeleopLinkState.ALIGNING
