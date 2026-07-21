"""Acceptance ⑥ — the head cameras are re-parented under the lifter in the variant.

The variant hangs ``camera_head_left``/``camera_head_right`` under
``openarm_lifter_link``; the upstream cell scene, which leaves them under the
world, raises a warning when audited. The structural claim is checked in the XML
and, where MuJoCo is present, confirmed against the compiled model's camera→body
map with the world pose preserved at lifter home.
"""

from __future__ import annotations

import pytest

from sim.mjcf.invariant import LIFTER_BODY, audit, head_camera_parents
from tests.wp0c03 import CELL_REPARENTED_XML, CELL_XML

HEAD_CAMERAS = ("camera_head_left", "camera_head_right")
HEAD_WORLD_POSE_AT_HOME = {
    "camera_head_left": (0.223, -0.0315, 1.45),
    "camera_head_right": (0.223, 0.0315, 1.45),
}
TOLERANCE = 1e-5


def test_variant_reparents_head_cameras_under_lifter() -> None:
    parents = head_camera_parents(CELL_REPARENTED_XML.read_text(encoding="utf-8"))
    assert parents == dict.fromkeys(HEAD_CAMERAS, LIFTER_BODY)


def test_variant_audit_is_clean() -> None:
    report = audit(CELL_REPARENTED_XML)
    assert report.ok
    assert report.warnings == []


def test_upstream_cell_warns_when_not_reparented() -> None:
    report = audit(CELL_XML)
    assert report.ok  # a warning, not a hard failure
    assert len(report.warnings) == 1
    assert LIFTER_BODY in report.warnings[0]


def test_compiled_variant_binds_cameras_to_lifter_body() -> None:
    mujoco = pytest.importorskip("mujoco")
    model = mujoco.MjModel.from_xml_path(str(CELL_REPARENTED_XML))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    lifter_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, LIFTER_BODY)
    for camera in HEAD_CAMERAS:
        camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
        assert model.cam_bodyid[camera_id] == lifter_id
        world = data.cam_xpos[camera_id]
        expected = HEAD_WORLD_POSE_AT_HOME[camera]
        assert all(abs(float(world[i]) - expected[i]) < TOLERANCE for i in range(3))
