"""RUNS-HERE ③ — a workspace-boundary target is projected onto the wall (`FR-TEL-036`).

The base-frame keep-in box projects an out-of-bounds EE target onto its nearest
boundary face (each axis clamped independently) and reports the violation, both as a
pure geometric operation and through the gate, where the projected point — not the
out-of-bounds target — becomes the command.
"""

from __future__ import annotations

import pytest

from backend.teleop.safety_gate.states import TeleopLinkState
from backend.teleop.safety_gate.workspace import WorkspaceBox
from tests.wp3b10.conftest import TICK_NS, make_gate, make_sample, pose_at

_BOX = WorkspaceBox(min_corner=(-1.0, -1.0, -1.0), max_corner=(1.0, 1.0, 1.0))


def test_inside_point_passes_unprojected() -> None:
    """A target inside the box is returned unchanged, not flagged."""
    result = _BOX.project((0.5, -0.5, 0.25))
    assert result.translation == (0.5, -0.5, 0.25)
    assert result.violated is False


def test_outside_point_projects_onto_the_nearest_face() -> None:
    """An out-of-bounds target is clamped per axis onto the boundary and flagged (③)."""
    result = _BOX.project((2.0, 0.5, -3.0))
    assert result.translation == (1.0, 0.5, -1.0)
    assert result.violated is True


def test_boundary_point_is_inside() -> None:
    """A point exactly on the boundary is inside — projection is inclusive."""
    assert _BOX.contains((1.0, 1.0, 1.0)) is True
    assert _BOX.project((1.0, 1.0, 1.0)).violated is False


def test_degenerate_box_is_rejected() -> None:
    """A box without positive extent on every axis is refused at construction."""
    with pytest.raises(ValueError, match="positive extent"):
        WorkspaceBox(min_corner=(0.0, 0.0, 0.0), max_corner=(0.0, 1.0, 1.0))


def test_gate_commands_the_projection_not_the_out_of_bounds_target() -> None:
    """Through the gate, an out-of-bounds follow target is commanded at the wall (③)."""
    gate = make_gate(seed_pose=pose_at((0.9, 0.0, 0.0)), box=_BOX)
    now = 1_000
    gate.step(now, pose_at((0.9, 0.0, 0.0)), sample=make_sample(now))
    gate.notify_alignment_converged(now)
    assert gate.state is TeleopLinkState.FOLLOWING

    now += TICK_NS
    out = gate.step(now, pose_at((5.0, 0.0, 0.0)), sample=make_sample(now))
    assert out.wall_violated is True
    # x is projected to the +x face (1.0); the command never leaves the box.
    assert gate.command.translation[0] == 1.0
    assert _BOX.contains(gate.command.translation)
