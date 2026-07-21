"""Acceptance ⑤ — the violation report carries all four FR-SIM-033 fields."""

from __future__ import annotations

from pathlib import Path

import mujoco

import sim.mjcf
from sim.dryrun.canon import ClampCanon, PositionCanon, VelocityCanon
from sim.dryrun.checks.cell_collision import check_cell_collision
from sim.dryrun.checks.position import check_position_limits
from sim.dryrun.topology import arm_joint_addresses
from sim.dryrun.violation import DryRunCheck
from tests.wp0c09._fixtures import CELL_COLLISION_XML, forward

_CELL = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"


def _assert_four_fields(violation: object) -> None:
    assert isinstance(violation.item, DryRunCheck)
    assert isinstance(violation.sim_t, float)
    assert isinstance(violation.joint, str) and violation.joint
    assert isinstance(violation.overage, float) and violation.overage >= 0.0


def test_per_joint_violation_reports_all_four_fields() -> None:
    """⑤ A position violation names the joint and the overage, at its sim time."""
    model = mujoco.MjModel.from_xml_path(str(_CELL))
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    address = {a.motor_key: a for a in arm_joint_addresses(model)}["left_joint_1"]
    data.qpos[address.qpos_adr] = 2.0
    mujoco.mj_forward(model, data)
    canon = ClampCanon(PositionCanon.MJCF, VelocityCanon.OPENARM_CONTROL)
    violations = check_position_limits(model, data, canon.resolve_position_bounds(model), 1.75)
    assert violations
    violation = violations[0]
    _assert_four_fields(violation)
    assert violation.joint == "left_joint_1"
    assert violation.sim_t == 1.75


def test_collision_violation_carries_the_geom_pair_as_its_locus() -> None:
    """⑤ A collision has no single joint, so the locus field holds the geom pair."""
    model, data = forward(CELL_COLLISION_XML)
    violations = check_cell_collision(model, data, 3.5)
    assert violations
    violation = violations[0]
    _assert_four_fields(violation)
    assert "<->" in violation.joint
    assert violation.sim_t == 3.5
