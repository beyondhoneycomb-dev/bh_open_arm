"""Acceptance ② — each of the six checks yields its own distinct item code.

Each check is provoked by a dedicated violation fixture and must return its own
``OA-DRY-00x`` code; the six together must be six distinct codes, never merged into
one "dry-run failed". Position, velocity, and lifter are driven out of bounds on the
real cell model; the collisions use real penetrating fixtures; torque uses an Nm
effort past its bound.
"""

from __future__ import annotations

from pathlib import Path

import mujoco

import sim.mjcf
from contracts.units.tags import Nm
from sim.dryrun.canon import ClampCanon, PositionCanon, VelocityCanon
from sim.dryrun.checks.cell_collision import check_cell_collision
from sim.dryrun.checks.lifter_stroke import check_lifter_stroke
from sim.dryrun.checks.position import check_position_limits
from sim.dryrun.checks.self_collision import check_self_collision
from sim.dryrun.checks.torque import check_torque_limits
from sim.dryrun.checks.velocity import check_velocity_limits
from sim.dryrun.topology import arm_joint_addresses, lifter_address
from sim.dryrun.violation import DryRunCheck
from tests.wp0c09._fixtures import CELL_COLLISION_XML, SELF_COLLISION_XML, forward

_CELL = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"


def _cell_model() -> tuple[mujoco.MjModel, mujoco.MjData]:
    model = mujoco.MjModel.from_xml_path(str(_CELL))
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    return model, data


def _address(model: mujoco.MjModel, motor_key: str) -> object:
    return {a.motor_key: a for a in arm_joint_addresses(model)}[motor_key]


def test_position_check_returns_its_own_code() -> None:
    model, data = _cell_model()
    address = _address(model, "left_joint_1")
    data.qpos[address.qpos_adr] = 2.0  # above the -3.4907..1.3963 range
    mujoco.mj_forward(model, data)
    canon = ClampCanon(PositionCanon.MJCF, VelocityCanon.OPENARM_CONTROL)
    violations = check_position_limits(model, data, canon.resolve_position_bounds(model), 0.5)
    assert {v.item for v in violations} == {DryRunCheck.POSITION_LIMIT}
    assert violations[0].joint == "left_joint_1"


def test_velocity_check_returns_its_own_code() -> None:
    model, data = _cell_model()
    address = _address(model, "left_joint_1")
    data.qvel[address.dof_adr] = 9.0  # above the openarm_control 1.57 rad/s bound
    mujoco.mj_forward(model, data)
    canon = ClampCanon(PositionCanon.MJCF, VelocityCanon.OPENARM_CONTROL)
    violations = check_velocity_limits(model, data, canon.resolve_velocity_limits(), 0.5)
    assert {v.item for v in violations} == {DryRunCheck.VELOCITY_LIMIT}


def test_torque_check_returns_its_own_code() -> None:
    efforts = {"left_joint_5": Nm(20.0)}  # above the +-7 Nm DM4310 bound
    limits = {"left_joint_5": Nm(7.0)}
    violations = check_torque_limits(efforts, limits, 0.5)
    assert {v.item for v in violations} == {DryRunCheck.TORQUE_LIMIT}


def test_cell_collision_check_returns_its_own_code() -> None:
    model, data = forward(CELL_COLLISION_XML)
    violations = check_cell_collision(model, data, 0.5)
    assert {v.item for v in violations} == {DryRunCheck.CELL_COLLISION}
    assert check_self_collision(model, data, 0.5) == ()


def test_self_collision_check_returns_its_own_code() -> None:
    model, data = forward(SELF_COLLISION_XML)
    violations = check_self_collision(model, data, 0.5)
    assert {v.item for v in violations} == {DryRunCheck.SELF_COLLISION}
    assert check_cell_collision(model, data, 0.5) == ()


def test_lifter_check_returns_its_own_code() -> None:
    model, data = _cell_model()
    data.qpos[lifter_address(model).qpos_adr] = 0.5  # above the 0.3 m stroke
    mujoco.mj_forward(model, data)
    violations = check_lifter_stroke(model, data, 0.5)
    assert {v.item for v in violations} == {DryRunCheck.LIFTER_STROKE}


def test_all_six_codes_are_distinct() -> None:
    """The six item codes are six distinct values, never collapsed into one."""
    codes = {check.value for check in DryRunCheck}
    assert len(codes) == 6
    assert codes == {f"OA-DRY-00{n}" for n in range(1, 7)}
