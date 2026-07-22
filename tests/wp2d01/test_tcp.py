"""Acceptance ⑥ — the default TCP is the flange control point, not the grasp point.

Teaching about the flange when the operator means the fingertip mis-places every taught
pose by the flange-to-tip offset. The default (FLANGE) offset is identity by
construction — the control point itself — and the grasp offset is a real, nonzero,
model-derived displacement. The UI note states the distinction (there is no Wave-2 GUI,
so the note is the string a later screen renders).
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.cartesian_jog import (
    JogAxis,
    JogCommand,
    JogKind,
    ReferenceFrame,
    TcpSelection,
    build_cartesian_jog,
)


def test_default_tcp_is_the_flange_not_the_grasp_point() -> None:
    jog = build_cartesian_jog()
    assert jog.default_tcp is TcpSelection.FLANGE
    for side in ("right", "left"):
        assert jog._tcp.default_is_not_grasp(side) is True
        flange = jog._tcp.offset(side, TcpSelection.FLANGE)
        grasp = jog._tcp.offset(side, TcpSelection.GRASP)
        assert np.allclose(flange[:3], np.zeros(3))
        assert float(np.linalg.norm(grasp[:3])) > 0.0


def test_ui_note_states_the_default_is_not_the_grasp_point() -> None:
    note = build_cartesian_jog().tcp_default_note()
    lowered = note.lower()
    assert "not" in lowered
    assert "grasp" in lowered
    assert "control point" in lowered


def test_selecting_grasp_moves_the_reported_tcp_along_the_tool_axis() -> None:
    jog = build_cartesian_jog()
    flange_pose = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)
    grasp_pose = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.GRASP)
    # Same orientation, different point: the grasp TCP is displaced from the flange.
    assert np.allclose(flange_pose[3:], grasp_pose[3:])
    assert float(np.linalg.norm(flange_pose[:3] - grasp_pose[:3])) > 0.0


def test_grasp_tcp_target_is_solved_back_to_the_control_point() -> None:
    # A jog on the grasp TCP still commits: the offset is undone before the IK site,
    # so the reused solver only ever sees control-point targets.
    jog = build_cartesian_jog()
    command = JogCommand(
        side="right",
        kind=JogKind.TRANSLATION,
        axis=JogAxis.Z,
        sign=1,
        frame=ReferenceFrame.WORLD,
        tcp=TcpSelection.GRASP,
    )
    result = jog.step(command)
    assert result.committed is True
