"""Acceptance ① — the FR-SIM-080 build order is enforced at runtime.

ArmSetup → jnt_range override → Kinematics. Building Kinematics before the override,
or overriding after Kinematics, must be rejected — the second because mink has
already snapshotted the un-overridden limits, which voids the override.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.config import ArmSetup
from openarm_control.kinematics import IKParams

from sim.ik.asset import (
    EE_FRAME_TYPE,
    HOME_KEYFRAME,
    LEFT_EE_SITE,
    RIGHT_EE_SITE,
    fixed_cell_xml,
)
from sim.ik.limits import all_soft_limits
from sim.ik.override import BuildStage, IkOrderError, OrderedIkBuild


def _fresh_setup() -> ArmSetup:
    return ArmSetup.from_args(
        xml=str(fixed_cell_xml()),
        mode="bimanual",
        frame_right=RIGHT_EE_SITE,
        frame_type_right=EE_FRAME_TYPE,
        frame_left=LEFT_EE_SITE,
        frame_type_left=EE_FRAME_TYPE,
        keyframe=HOME_KEYFRAME,
    )


def test_kinematics_before_override_is_rejected() -> None:
    build = OrderedIkBuild(_fresh_setup())
    assert build.stage is BuildStage.SETUP_CREATED
    with pytest.raises(IkOrderError, match="before the jnt_range override"):
        build.build_kinematics(IKParams())


def test_override_after_kinematics_is_rejected() -> None:
    build = OrderedIkBuild(_fresh_setup())
    build.override_joint_ranges(all_soft_limits())
    build.build_kinematics(IKParams())
    assert build.stage is BuildStage.KINEMATICS_BUILT
    with pytest.raises(IkOrderError, match="after Kinematics"):
        build.override_joint_ranges(all_soft_limits())


def test_correct_order_advances_the_stage_machine() -> None:
    build = OrderedIkBuild(_fresh_setup())
    build.override_joint_ranges(all_soft_limits())
    assert build.stage is BuildStage.RANGE_OVERRIDDEN
    kinematics = build.build_kinematics(IKParams())
    assert build.stage is BuildStage.KINEMATICS_BUILT
    assert kinematics is not None


def test_double_override_is_rejected() -> None:
    build = OrderedIkBuild(_fresh_setup())
    build.override_joint_ranges(all_soft_limits())
    with pytest.raises(IkOrderError, match="twice"):
        build.override_joint_ranges(all_soft_limits())
