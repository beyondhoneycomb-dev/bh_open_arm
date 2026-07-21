"""Clamp-canon selection is mandatory — refuse to run when unselected (FR-SIM-132)."""

from __future__ import annotations

from pathlib import Path

import mujoco
import pytest

import sim.mjcf
from sim.dryrun.canon import (
    ClampCanon,
    ClampCanonUnselectedError,
    PositionCanon,
    VelocityCanon,
)

_CELL = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"


def test_unselected_position_canon_refuses() -> None:
    """FR-SIM-031/132: no position canon selected → refuse to build a runnable canon."""
    with pytest.raises(ClampCanonUnselectedError):
        ClampCanon(position=PositionCanon.UNSELECTED, velocity=VelocityCanon.URDF)


def test_unselected_velocity_canon_refuses() -> None:
    """FR-SIM-032/132: no velocity canon selected → refuse."""
    with pytest.raises(ClampCanonUnselectedError):
        ClampCanon(position=PositionCanon.MJCF, velocity=VelocityCanon.UNSELECTED)


def test_default_construction_is_unselected_and_refuses() -> None:
    """The default canon is unselected on both axes and refuses."""
    with pytest.raises(ClampCanonUnselectedError):
        ClampCanon()


def test_table_requiring_position_canon_without_table_refuses() -> None:
    """URDF/LeRobot position canon needs an explicit table, else refuse."""
    with pytest.raises(ClampCanonUnselectedError):
        ClampCanon(position=PositionCanon.URDF, velocity=VelocityCanon.URDF)


def test_selected_canon_resolves_nonempty_tables() -> None:
    """A fully selected canon resolves both limit tables over the real model."""
    canon = ClampCanon(position=PositionCanon.MJCF, velocity=VelocityCanon.OPENARM_CONTROL)
    model = mujoco.MjModel.from_xml_path(str(_CELL))
    bounds = canon.resolve_position_bounds(model)
    velocity = canon.resolve_velocity_limits()
    assert len(bounds) == 14
    assert len(velocity) == 14
    lower, upper = bounds["left_joint_1"]
    assert lower < upper


def test_velocity_candidate_tables_differ() -> None:
    """The two velocity candidates are genuinely different tables (Q4 undecided)."""
    urdf = ClampCanon(PositionCanon.MJCF, VelocityCanon.URDF).resolve_velocity_limits()
    control = ClampCanon(
        PositionCanon.MJCF, VelocityCanon.OPENARM_CONTROL
    ).resolve_velocity_limits()
    assert urdf["left_joint_1"] != control["left_joint_1"]
