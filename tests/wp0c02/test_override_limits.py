"""Acceptance ② and ③ — override equals LeRobot limits, and a mismatch rejects launch.

② After the override, ``setup.model.jnt_range`` equals the LeRobot ``joint_limits``
   (radian-converted) for every joint LeRobot limits.
③ A jnt_range that disagrees with the LeRobot limits is a launch-time reject.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

import mujoco
from openarm_control.config import ArmSetup

from sim.ik.asset import (
    EE_FRAME_TYPE,
    HOME_KEYFRAME,
    LEFT_EE_SITE,
    RIGHT_EE_SITE,
    fixed_cell_xml,
)
from sim.ik.limits import all_soft_limits, soft_limits
from sim.ik.override import (
    LimitMismatchError,
    overwrite_jnt_range,
    verify_ranges_match,
)

_TOL = 1e-9


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


def test_override_matches_lerobot_limits_all_joints() -> None:
    setup = _fresh_setup()
    limits = all_soft_limits()
    overwrite_jnt_range(setup, limits)

    for limit in limits:
        jid = mujoco.mj_name2id(setup.model, mujoco.mjtObj.mjOBJ_JOINT, limit.mjcf_joint)
        assert jid >= 0
        lower = float(setup.model.jnt_range[jid][0])
        upper = float(setup.model.jnt_range[jid][1])
        assert lower == pytest.approx(limit.lower_rad.value, abs=_TOL)
        assert upper == pytest.approx(limit.upper_rad.value, abs=_TOL)
        # The written radians are the LeRobot degrees, converted once.
        assert lower == pytest.approx(math.radians(limit.lower_deg.value), abs=_TOL)
    verify_ranges_match(setup, limits)


def test_override_changes_the_mjcf_ranges() -> None:
    # The MJCF ships wider limits than LeRobot's soft clamp (right j1 -80..200 deg vs
    # -75..75); the override must actually narrow them, not be a no-op.
    setup = _fresh_setup()
    right_j1 = soft_limits("right")[0]
    jid = mujoco.mj_name2id(setup.model, mujoco.mjtObj.mjOBJ_JOINT, right_j1.mjcf_joint)
    before = float(setup.model.jnt_range[jid][1])
    overwrite_jnt_range(setup, all_soft_limits())
    after = float(setup.model.jnt_range[jid][1])
    assert after != pytest.approx(before, abs=1e-6)
    assert after == pytest.approx(right_j1.upper_rad.value, abs=_TOL)


def test_mismatched_range_rejects_launch() -> None:
    setup = _fresh_setup()
    limits = all_soft_limits()
    overwrite_jnt_range(setup, limits)
    # Corrupt one joint's range so it no longer matches the LeRobot limit.
    jid = mujoco.mj_name2id(setup.model, mujoco.mjtObj.mjOBJ_JOINT, "openarm_right_joint3")
    setup.model.jnt_range[jid][1] += 0.5
    with pytest.raises(LimitMismatchError, match="openarm_right_joint3"):
        verify_ranges_match(setup, limits)


def test_verify_passes_on_exact_override() -> None:
    setup = _fresh_setup()
    limits = all_soft_limits()
    overwrite_jnt_range(setup, limits)
    verify_ranges_match(setup, limits)
