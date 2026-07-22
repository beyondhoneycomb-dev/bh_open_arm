"""Shared builders for the WP-2A-00 interlock acceptance tests.

The six per-check violations are produced by driving the *committed Wave 0-C
checkers* over crafted states, not by fabricating ``Violation`` records: acceptance
① demands fault injection over those checkers, so the interlock is proven to block
on what they actually report. Position, velocity, and lifter are driven out of
bounds on the real cell model; the two collisions use real penetrating fixtures;
torque uses an effort past its bound. Each violation therefore carries a genuine
item / sim_t / joint / overage for the block report to preserve.
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
from sim.dryrun.topology import JointAddress, arm_joint_addresses, lifter_address
from sim.dryrun.violation import DryRunCheck, DryRunVerdict, Violation

_CELL = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"

# A collision-free, within-limit pose: raised arms so link5 clears the cell table and
# the gravity holding torque stays under the limits — the runner's passing case.
CLEAN_POSE = {
    "left_joint_2": -1.4,
    "right_joint_2": 1.4,
    "left_joint_4": 2.0,
    "right_joint_4": 2.0,
}

# A group-3 robot box driven into a group-4 cell box (0.05 m overlap): a cell strike.
_CELL_COLLISION_XML = """
<mujoco>
  <worldbody>
    <geom name="cellbox" type="box" size="0.1 0.1 0.1" pos="0 0 0"
          group="4" contype="1" conaffinity="1"/>
    <body name="robot" pos="0.15 0 0">
      <freejoint/>
      <geom name="robotbox" type="box" size="0.1 0.1 0.1"
            group="3" contype="1" conaffinity="1"/>
    </body>
  </worldbody>
</mujoco>
"""

# Two group-3 robot boxes driven together (0.05 m overlap): a self-strike.
_SELF_COLLISION_XML = """
<mujoco>
  <worldbody>
    <geom name="linkA" type="box" size="0.1 0.1 0.1" pos="0 0 0"
          group="3" contype="1" conaffinity="1"/>
    <body name="linkB" pos="0.15 0 0">
      <freejoint/>
      <geom name="linkbbox" type="box" size="0.1 0.1 0.1"
            group="3" contype="1" conaffinity="1"/>
    </body>
  </worldbody>
</mujoco>
"""

# The sim time stamped on each injected violation, so the block report is checked to
# preserve it rather than losing it to a merge.
INJECT_SIM_T = 0.5


def make_canon() -> ClampCanon:
    """Return a fully selected canon (MJCF position, openarm_control velocity)."""
    return ClampCanon(position=PositionCanon.MJCF, velocity=VelocityCanon.OPENARM_CONTROL)


def cell_model() -> tuple[mujoco.MjModel, mujoco.MjData]:
    """Compile the real cell model and reset it for a hand-set state."""
    model = mujoco.MjModel.from_xml_path(str(_CELL))
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    return model, data


def _forward(xml: str) -> tuple[mujoco.MjModel, mujoco.MjData]:
    """Compile an inline model and forward-evaluate it once for contact readout."""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data


def _address(model: mujoco.MjModel, motor_key: str) -> JointAddress:
    """Resolve one arm joint's address by motor key."""
    return {a.motor_key: a for a in arm_joint_addresses(model)}[motor_key]


def _position_violation() -> tuple[Violation, ...]:
    model, data = cell_model()
    address = _address(model, "left_joint_1")
    data.qpos[address.qpos_adr] = 2.0  # above the -3.49..1.40 range
    mujoco.mj_forward(model, data)
    bounds = make_canon().resolve_position_bounds(model)
    return check_position_limits(model, data, bounds, INJECT_SIM_T)


def _velocity_violation() -> tuple[Violation, ...]:
    model, data = cell_model()
    address = _address(model, "left_joint_1")
    data.qvel[address.dof_adr] = 9.0  # above the openarm_control bound
    mujoco.mj_forward(model, data)
    limits = make_canon().resolve_velocity_limits()
    return check_velocity_limits(model, data, limits, INJECT_SIM_T)


def _torque_violation() -> tuple[Violation, ...]:
    return check_torque_limits({"left_joint_5": Nm(20.0)}, {"left_joint_5": Nm(7.0)}, INJECT_SIM_T)


def _cell_collision_violation() -> tuple[Violation, ...]:
    model, data = _forward(_CELL_COLLISION_XML)
    return check_cell_collision(model, data, INJECT_SIM_T)


def _self_collision_violation() -> tuple[Violation, ...]:
    model, data = _forward(_SELF_COLLISION_XML)
    return check_self_collision(model, data, INJECT_SIM_T)


def _lifter_violation() -> tuple[Violation, ...]:
    model, data = cell_model()
    data.qpos[lifter_address(model).qpos_adr] = 0.5  # above the 0.3 m stroke
    mujoco.mj_forward(model, data)
    return check_lifter_stroke(model, data, INJECT_SIM_T)


def real_violations_by_check() -> dict[DryRunCheck, tuple[Violation, ...]]:
    """Return one real violation tuple per check, from the committed Wave 0-C checkers.

    Returns:
        (dict) Each of the six ``DryRunCheck`` codes to the violations its committed
        checker reports on a crafted state — genuine fault injection, one per check.
    """
    return {
        DryRunCheck.POSITION_LIMIT: _position_violation(),
        DryRunCheck.VELOCITY_LIMIT: _velocity_violation(),
        DryRunCheck.TORQUE_LIMIT: _torque_violation(),
        DryRunCheck.CELL_COLLISION: _cell_collision_violation(),
        DryRunCheck.SELF_COLLISION: _self_collision_violation(),
        DryRunCheck.LIFTER_STROKE: _lifter_violation(),
    }


def verdict_of(violations: tuple[Violation, ...]) -> DryRunVerdict:
    """Wrap injected violations into a verdict the interlock consumes."""
    return DryRunVerdict(violations=violations, asset_digest="wp2a00-fixture", backend="mujoco")
