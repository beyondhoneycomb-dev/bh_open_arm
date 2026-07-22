"""Reference frames — base / tool / world jog semantics (02b §4.1 WP-2D-01 산출).

The v2 cell mounts the arm base unrotated and lifts it along world z, so world- and
base-frame *deltas* coincide and differ only by the lifter origin (the q_lift term).
The tool frame is the one that rotates with the TCP, so a tool-axis jog moves along a
different world direction. Frame expression round-trips exactly for base and tool.
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


def _translate(side: str, axis: JogAxis, frame: ReferenceFrame) -> JogCommand:
    return JogCommand(side=side, kind=JogKind.TRANSLATION, axis=axis, sign=1, frame=frame)


def test_world_and_base_translation_deltas_coincide() -> None:
    # The base is mounted unrotated, so a +z jog in world and in base commit the same
    # arm state from the same seed. This is a property of the asset, read back below.
    world_jog = build_cartesian_jog()
    base_jog = build_cartesian_jog()
    world_result = world_jog.step(_translate("right", JogAxis.Z, ReferenceFrame.WORLD))
    base_result = base_jog.step(_translate("right", JogAxis.Z, ReferenceFrame.BASE))
    assert world_result.committed and base_result.committed
    assert np.allclose(world_jog.committed_solution(), base_jog.committed_solution(), atol=1e-6)


def test_base_frame_orientation_is_identity_in_this_asset() -> None:
    jog = build_cartesian_jog()
    base_pose = jog._frames.world_from_base("right", jog.q_lift)
    assert np.allclose(base_pose[3:], [1.0, 0.0, 0.0, 0.0])


def test_tool_translation_moves_along_a_different_world_direction() -> None:
    world_jog = build_cartesian_jog()
    tool_jog = build_cartesian_jog()
    start = world_jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)[:3]

    world_jog.step(_translate("right", JogAxis.Z, ReferenceFrame.WORLD))
    tool_jog.step(_translate("right", JogAxis.Z, ReferenceFrame.TOOL))

    world_delta = world_jog.current_pose("right", ReferenceFrame.WORLD)[:3] - start
    tool_delta = tool_jog.current_pose("right", ReferenceFrame.WORLD)[:3] - start
    # The tool z-axis is not aligned with world z at the home pose, so the directions
    # differ — the tool frame is genuinely distinct from world.
    world_dir = world_delta / np.linalg.norm(world_delta)
    tool_dir = tool_delta / np.linalg.norm(tool_delta)
    assert not np.allclose(world_dir, tool_dir, atol=1e-2)


@pytest.mark.parametrize("frame", [ReferenceFrame.BASE, ReferenceFrame.TOOL])
def test_frame_expression_round_trips(frame: ReferenceFrame) -> None:
    jog = build_cartesian_jog()
    jog.set_q_lift(0.2)
    world = jog.current_pose("right", ReferenceFrame.WORLD, TcpSelection.FLANGE)
    in_frame = jog._world_to_frame("right", world, frame)
    back = jog._frame_to_world("right", in_frame, frame)
    assert np.allclose(back[:3], world[:3], atol=1e-9)
