"""Acceptance ① — a violation in any of the six checks hard-blocks real transmission.

For each of the six committed Wave 0-C checks, an injected violation is gated through
the interlock: real-send must be blocked, the real transition must refuse, and the
block report must preserve the violation's item / sim_t / joint / overage. The
passing path is exercised too, so the block is proven not to be rigged always-on: a
clean verdict arms the barrier and its guarded real-send starter runs exactly once,
holding the grant.
"""

from __future__ import annotations

import pytest

from backend.interlock import (
    InterlockState,
    RealSendBarrier,
    RealTransitionBlockedError,
)
from sim.dryrun.interlock import TransmissionGrant
from sim.dryrun.runner import DryRunRunner, Waypoint
from sim.dryrun.violation import DryRunCheck
from tests.wp2a00._fixtures import (
    CLEAN_POSE,
    INJECT_SIM_T,
    make_canon,
    real_violations_by_check,
    verdict_of,
)


@pytest.mark.parametrize("check", list(DryRunCheck))
def test_each_check_violation_blocks_real_send(check: DryRunCheck) -> None:
    """A violation in any one check blocks real-send and refuses the real transition."""
    violations = real_violations_by_check()[check]
    assert violations, f"the committed checker for {check.value} produced no violation to inject"

    barrier = RealSendBarrier()
    decision = barrier.gate(verdict_of(violations))

    assert decision.state is InterlockState.BLOCKED
    assert decision.permits_real_send is False
    assert barrier.permits_real_send is False
    with pytest.raises(RealTransitionBlockedError):
        barrier.authorize_real_transition()


@pytest.mark.parametrize("check", list(DryRunCheck))
def test_block_report_preserves_item_simt_joint_overage(check: DryRunCheck) -> None:
    """The block report keeps each violation's four FR-SIM-033 fields (① evidence)."""
    violations = real_violations_by_check()[check]
    decision = RealSendBarrier().gate(verdict_of(violations))

    recorded = decision.blocking_violations
    assert {v.item for v in recorded} == {v.item for v in violations}
    assert check in {v.item for v in recorded}
    for violation in recorded:
        assert violation.sim_t == INJECT_SIM_T
        assert violation.joint, "the implicated joint/geom-pair locus must be recorded"
        assert violation.overage > 0.0, "the overage magnitude must be recorded"


def test_guarded_real_send_never_starts_when_blocked() -> None:
    """The real-send starter is never invoked on a blocked verdict — the hard block bites."""
    violations = real_violations_by_check()[DryRunCheck.TORQUE_LIMIT]
    barrier = RealSendBarrier()
    barrier.gate(verdict_of(violations))

    started: list[TransmissionGrant] = []
    with pytest.raises(RealTransitionBlockedError):
        barrier.guard_real_transition(started.append)
    assert started == [], "a blocked barrier must not run the real-send starter"


def test_clean_dry_run_arms_and_starts_real_send_once() -> None:
    """A clean pose arms the barrier; the guarded starter runs once, holding the grant."""
    barrier = RealSendBarrier()
    runner = DryRunRunner(make_canon())
    decision = barrier.run_and_gate(runner, [Waypoint(sim_t=0.0, positions_rad=CLEAN_POSE)])

    assert decision.state is InterlockState.ARMED
    assert decision.permits_real_send is True
    assert barrier.permits_real_send is True

    started: list[TransmissionGrant] = []
    barrier.guard_real_transition(started.append)
    assert len(started) == 1
    assert started[0].via_modal_confirm is False
    assert started[0] is barrier.authorize_real_transition()
