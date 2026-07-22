"""Shared builders for the WP-2C-07 virtual-wall acceptance tests.

The tests run over the *committed* cell asset (`sim/mjcf/v2/cell.xml`, WP-0C-03,
read-only), not a fabricated model, so "walls off refuses the check" and "the table
stays active" are proven on the real scene a real cell-collision check reads. The home
keyframe is a collision-free pose; the all-zeros reset drives the arms into the
now-active walls, so a walls-on check has both a genuine pass and a genuine detection.
"""

from __future__ import annotations

from pathlib import Path

import mujoco

import sim.mjcf

_CELL = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"

# Keyframe 0 of the committed cell asset is the raised "home" pose, clear of every wall.
_HOME_KEYFRAME = 0


def cell_model() -> mujoco.MjModel:
    """Compile the committed cell asset (walls ship active)."""
    return mujoco.MjModel.from_xml_path(str(_CELL))


def home_state(model: mujoco.MjModel) -> mujoco.MjData:
    """Return a forward-evaluated state at the collision-free home keyframe."""
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, _HOME_KEYFRAME)
    mujoco.mj_forward(model, data)
    return data


def zeros_state(model: mujoco.MjModel) -> mujoco.MjData:
    """Return a forward-evaluated all-zeros state, which penetrates the cell walls."""
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    return data


def geom_masks(model: mujoco.MjModel, name: str) -> tuple[int, int]:
    """Return a named geom's (contype, conaffinity) collision masks."""
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
    return int(model.geom_contype[geom_id]), int(model.geom_conaffinity[geom_id])
