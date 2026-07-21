"""Acceptance ⑧ — the lifter stroke boundary values 0 and 0.3 m."""

from __future__ import annotations

from pathlib import Path

import mujoco
import pytest

import sim.mjcf
from sim.dryrun.checks.lifter_stroke import check_lifter_stroke
from sim.dryrun.topology import lifter_address
from sim.dryrun.violation import DryRunCheck

_CELL = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"


def _cell_at_lifter(position: float) -> tuple[mujoco.MjModel, mujoco.MjData]:
    model = mujoco.MjModel.from_xml_path(str(_CELL))
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    data.qpos[lifter_address(model).qpos_adr] = position
    mujoco.mj_forward(model, data)
    return model, data


@pytest.mark.parametrize("position", [0.0, 0.3])
def test_boundary_values_are_on_stroke(position: float) -> None:
    """⑧ Exactly 0 and 0.3 m are on-stroke and pass."""
    model, data = _cell_at_lifter(position)
    assert check_lifter_stroke(model, data, 0.0) == ()


@pytest.mark.parametrize("position,overage", [(0.35, 0.05), (-0.05, 0.05)])
def test_off_stroke_positions_violate(position: float, overage: float) -> None:
    """⑧ Travel past either end is one lifter-stroke violation, overage in metres."""
    model, data = _cell_at_lifter(position)
    violations = check_lifter_stroke(model, data, 2.0)
    assert len(violations) == 1
    assert violations[0].item is DryRunCheck.LIFTER_STROKE
    assert violations[0].sim_t == 2.0
    assert violations[0].overage == pytest.approx(overage, abs=1e-6)
