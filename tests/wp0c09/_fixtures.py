"""Shared fixtures for the WP-0C-09 acceptance tests.

The collision fixtures are real MuJoCo models with penetrating group-3 (robot) and
group-4 (cell) box geoms, so the collision checks are exercised against genuine
contacts rather than mocked ones. ``CLEAN_POSE`` is an empirically collision-free,
within-limit arm configuration used to prove the runner can return a passing
verdict — that the hard block is not rigged to always fire.
"""

from __future__ import annotations

import mujoco

from sim.dryrun.canon import ClampCanon, PositionCanon, VelocityCanon

# A group-3 robot box driven into a group-4 cell box (0.05 m overlap): a cell strike.
CELL_COLLISION_XML = """
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
SELF_COLLISION_XML = """
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

# A collision-free, within-limit pose: arms raised (joint2 mirrored, elbow bent), so
# link5 clears the cell table and the gravity holding torque stays under the limits.
CLEAN_POSE = {
    "left_joint_2": -1.4,
    "right_joint_2": 1.4,
    "left_joint_4": 2.0,
    "right_joint_4": 2.0,
}


def make_canon() -> ClampCanon:
    """Return a fully selected canon (MJCF position, openarm_control velocity)."""
    return ClampCanon(position=PositionCanon.MJCF, velocity=VelocityCanon.OPENARM_CONTROL)


def forward(xml: str) -> tuple[mujoco.MjModel, mujoco.MjData]:
    """Compile an inline model and forward-evaluate it once for contact readout."""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data
