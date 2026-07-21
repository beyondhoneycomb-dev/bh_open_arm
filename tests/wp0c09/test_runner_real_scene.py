"""The dry-run runner over the real cell scene: it passes clean, blocks on violation.

Also the end-to-end interlock path: a passing verdict authorizes transmission, a
failing one hard-blocks. The failing case is driven from the *real* asset, which
carries a genuine home-region penetration and a real gravity over-torque at the
extended pose — so the block is proven against real detections, not synthetic ones.
"""

from __future__ import annotations

import pytest

from sim.dryrun.interlock import HardBlockError, authorize_transmission
from sim.dryrun.runner import DryRunRunner, Waypoint
from sim.dryrun.violation import DryRunCheck
from tests.wp0c09._fixtures import CLEAN_POSE, make_canon


def test_runner_passes_a_clean_pose_and_authorizes() -> None:
    """The runner is not rigged to always fail: a clean pose passes and authorizes."""
    runner = DryRunRunner(make_canon())
    verdict = runner.run_trajectory([Waypoint(sim_t=0.0, positions_rad=CLEAN_POSE)])
    assert verdict.passed
    assert verdict.backend == "mujoco"
    grant = authorize_transmission(verdict)
    assert grant.via_modal_confirm is False


def test_runner_detects_real_violations_and_hard_blocks() -> None:
    """A bad pose yields real, distinct violations, each sim-timed, and hard-blocks."""
    runner = DryRunRunner(make_canon())
    # An extended zero pose: link5 penetrates the cell table and the shoulders exceed
    # their holding-torque limit under gravity — both real detections on the asset.
    verdict = runner.run_trajectory([Waypoint(sim_t=1.0, positions_rad={"left_joint_1": 0.0})])
    assert not verdict.passed
    items = set(verdict.items_hit())
    assert DryRunCheck.CELL_COLLISION in items
    assert DryRunCheck.TORQUE_LIMIT in items
    assert all(v.sim_t == 1.0 for v in verdict.violations)
    with pytest.raises(HardBlockError):
        authorize_transmission(verdict)


def test_runner_refuses_an_unselected_canon() -> None:
    """FR-SIM-132: without a selected canon the runner cannot even be built."""
    from sim.dryrun.canon import ClampCanon, ClampCanonUnselectedError

    with pytest.raises(ClampCanonUnselectedError):
        DryRunRunner(ClampCanon())


def test_waypoint_from_ctr_act_action_is_validated() -> None:
    """The dry-run consumes the CTR-ACT action (WP-0A-02) it gates, deg→rad."""
    from contracts.action.channels import AcceptedPositionAction
    from contracts.units.tags import Deg

    action = AcceptedPositionAction(values=tuple(Deg(0.0) for _ in range(16)))
    waypoint = Waypoint.from_accepted_action(action, sim_t=0.5)
    assert len(waypoint.positions_rad) == 16
    assert waypoint.sim_t == 0.5
    verdict = DryRunRunner(make_canon()).run_trajectory([waypoint])
    assert verdict.backend == "mujoco"  # the runner accepted the CTR-ACT-derived waypoint


def test_waypoint_from_ik_outcome_bridges_wp0c02() -> None:
    """The dry-run consumes the IK adapter's output (WP-0C-02) as a trajectory."""
    from contracts.action.channels import AcceptedPositionAction
    from contracts.units.tags import Deg
    from sim.ik.adapter import IkOutcome

    accepted = AcceptedPositionAction(values=tuple(Deg(float(i)) for i in range(16)))
    outcome = IkOutcome(accepted=accepted, held=False, faults=(), solution_rad=None)
    waypoint = Waypoint.from_ik_outcome(outcome, sim_t=1.0)
    assert len(waypoint.positions_rad) == 16
    assert waypoint.sim_t == 1.0
    with pytest.raises(TypeError):
        Waypoint.from_ik_outcome("not-an-outcome")
    held = IkOutcome(accepted=None, held=True, faults=(), solution_rad=None)
    with pytest.raises(ValueError, match="nothing to dry-run"):
        Waypoint.from_ik_outcome(held)
