"""RUNS-HERE ② — recovery never auto-resumes; it must pass through ALIGNING.

`FR-TEL-082` / `05` §4.2 #1 and #3: a lost link or a fault holds, and the *only* way
back to following is an explicit operator re-engage that lands in ALIGNING — never a
direct resume. Link recovery on its own does nothing; an auto-resume is the defect.
The re-engage is refused while the link is still lost, and — the superior gate —
refused while the deadman lease latch is held (link recovery is not re-arming).
"""

from __future__ import annotations

import pytest

from backend.teleop.safety_gate.heartbeat import LinkHealth
from backend.teleop.safety_gate.states import (
    ForbiddenTransitionError,
    LinkNotLiveError,
    RearmRequiredError,
    TeleopLinkState,
)
from tests.wp3b10.conftest import (
    TICK_NS,
    FakeLease,
    make_gate,
    make_sample,
    pose_at,
)

_LOSS_ADVANCE_NS = 20 * TICK_NS


def _to_following(gate, start_ns: int) -> int:
    """Align to FOLLOWING with a live link; return the current clock."""
    now = start_ns
    gate.step(now, pose_at((0.0, 0.0, 0.0)), sample=make_sample(now))
    gate.notify_alignment_converged(now)
    assert gate.state is TeleopLinkState.FOLLOWING
    return now


def _to_link_lost(gate, now: int) -> int:
    """Drop the heartbeat until the gate is in LINK_LOST; return the current clock."""
    now += _LOSS_ADVANCE_NS
    out = gate.step(now, pose_at((0.0, 0.0, 0.0)))
    assert out.state is TeleopLinkState.LINK_LOST
    return now


def test_link_recovery_alone_does_not_resume_following() -> None:
    """After the link comes back, the gate stays held until an explicit re-engage (②)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now = _to_following(gate, start_ns=1_000)
    now = _to_link_lost(gate, now)

    # Restore the link: fresh OK frames arrive again for many ticks.
    for _ in range(30):
        now += TICK_NS
        out = gate.step(now, pose_at((0.1, 0.0, 0.0)), sample=make_sample(now))
        assert out.link_health is LinkHealth.LIVE  # the link is demonstrably healthy
        assert out.state is TeleopLinkState.LINK_LOST  # yet it does NOT auto-resume
    assert gate.state is TeleopLinkState.LINK_LOST


def test_reengage_routes_through_aligning_never_direct_to_following() -> None:
    """Explicit re-engage lands in ALIGNING; FOLLOWING is reached only after convergence (②)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now = _to_following(gate, start_ns=1_000)
    now = _to_link_lost(gate, now)

    # Restore the link, then the operator re-engages.
    now += TICK_NS
    gate.step(now, pose_at((0.1, 0.0, 0.0)), sample=make_sample(now))
    gate.request_reengage(now)
    assert gate.state is TeleopLinkState.ALIGNING  # not FOLLOWING

    # Following is entered only when the aligner reports convergence.
    now += TICK_NS
    gate.step(now, pose_at((0.1, 0.0, 0.0)), sample=make_sample(now))
    gate.notify_alignment_converged(now)
    assert gate.state is TeleopLinkState.FOLLOWING


def test_reengage_refused_while_link_still_lost() -> None:
    """A re-engage requires the VR link to be back (`05` §4.2/S5 exit) (②)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now = _to_following(gate, start_ns=1_000)
    now = _to_link_lost(gate, now)
    with pytest.raises(LinkNotLiveError):
        gate.request_reengage(now)
    assert gate.state is TeleopLinkState.LINK_LOST


def test_reengage_refused_while_lease_latch_held() -> None:
    """While the deadman lease latch is held, ALIGNING entry itself is refused (②).

    The lease re-arm handshake is superior to link recovery: even with the VR link
    back and the operator re-engaging, a held latch blocks entry into ALIGNING until
    the deadman is re-armed (`WP-2A-02` outranks link recovery).
    """
    lease = FakeLease(latched=True)
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)), lease=lease)
    now = _to_following(gate, start_ns=1_000)
    now = _to_link_lost(gate, now)

    # Link is back, but the lease is latched.
    now += TICK_NS
    gate.step(now, pose_at((0.1, 0.0, 0.0)), sample=make_sample(now))
    with pytest.raises(RearmRequiredError):
        gate.request_reengage(now)
    assert gate.state is TeleopLinkState.LINK_LOST

    # Once the deadman re-arm clears the latch, the same re-engage is permitted.
    lease.latched = False
    gate.request_reengage(now)
    assert gate.state is TeleopLinkState.ALIGNING


def test_alignment_convergence_cannot_skip_a_hold() -> None:
    """`notify_alignment_converged` is refused from a hold — a hold can only re-engage (②)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now = _to_following(gate, start_ns=1_000)
    now = _to_link_lost(gate, now)
    with pytest.raises(ForbiddenTransitionError):
        gate.notify_alignment_converged(now)


def test_reengage_refused_when_not_in_a_hold() -> None:
    """Re-engage is only valid out of a hold, not from FOLLOWING or ALIGNING (②)."""
    gate = make_gate(seed_pose=pose_at((0.0, 0.0, 0.0)))
    now = _to_following(gate, start_ns=1_000)
    with pytest.raises(ForbiddenTransitionError):
        gate.request_reengage(now)
