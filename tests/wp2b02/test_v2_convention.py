"""WP-2B-02 consumes WP-2B-01: gravity is computed in the v2 joint convention, verified at load.

Two ties to WP-2B-01:

* Physics — feeding a v1 pose without WP-2B-01's `+pi/2` joint2 shift changes the shoulder
  gravity term (the sin<->cos swap of spec 12 §2.6). The `JointFrameConverter` bridge is what
  makes the two agree, which is exactly why WP-2B-02 depends on WP-2B-01.
* Guard — `ArmModel` refuses a model whose reference arm is not in the v2 convention, checked
  against WP-2B-01's frozen `V2_JOINT_AXES` and `V2_JOINT2_RANGE_RAD`.
"""

from __future__ import annotations

import mujoco
import pytest

from backend.dynamics import JointFrameConverter
from backend.dynamics.constants import V2_JOINT_AXES
from backend.gravity import GravityBackendError, select_backend
from backend.gravity.model import _verify_v2_convention

_AXIS_STRINGS = tuple(f"{axis[0]} {axis[1]} {axis[2]}" for axis in V2_JOINT_AXES)


def _synthetic_right_arm_xml(joint2_range: str, joint1_axis: str) -> str:
    """Build a minimal compileable MJCF with the seven right-arm joints for the guard test.

    Only `jnt_axis` and joint2's `jnt_range` are read by the check, but each body still needs a
    geom so the model compiles with non-zero mass.
    """
    axes = (joint1_axis, *_AXIS_STRINGS[1:])
    ranges = ["-1.5 1.5"] * 7
    ranges[1] = joint2_range
    body_open = ""
    body_close = ""
    for index in range(7):
        body_open += (
            f'<body name="rb{index}" pos="0 0 -0.1">'
            f'<joint name="openarm_right_joint{index + 1}" type="hinge" limited="true" '
            f'axis="{axes[index]}" range="{ranges[index]}"/>'
            f'<geom type="box" size="0.02 0.02 0.05"/>'
        )
        body_close += "</body>"
    # angle="radian" so the ranges are read as radians, matching the real v2 asset; without it
    # mujoco defaults to degrees and the joint2 range would be silently rescaled.
    return (
        f'<mujoco><compiler angle="radian"/><worldbody>{body_open}{body_close}</worldbody></mujoco>'
    )


def test_real_v2_model_passes_the_convention_check() -> None:
    """Building a backend on the committed asset runs the guard and succeeds."""
    assert select_backend().backend_id.value == "MUJOCO_V2"


def test_v1_range_model_is_refused() -> None:
    """A model with the v1 joint2 range (differing by ~pi/2) is refused."""
    model = mujoco.MjModel.from_xml_string(
        _synthetic_right_arm_xml("-1.745329 1.745329", _AXIS_STRINGS[0])
    )
    with pytest.raises(GravityBackendError, match="joint2 range"):
        _verify_v2_convention(model)


def test_wrong_axis_model_is_refused() -> None:
    """A model whose joint1 axis disagrees with the v2 reference is refused."""
    model = mujoco.MjModel.from_xml_string(_synthetic_right_arm_xml("-0.17453 3.3161", "1 0 0"))
    with pytest.raises(GravityBackendError, match="axis"):
        _verify_v2_convention(model)


def test_correct_synthetic_model_passes() -> None:
    """The synthetic model with v2 axes and joint2 range passes the same check."""
    model = mujoco.MjModel.from_xml_string(
        _synthetic_right_arm_xml("-0.17453 3.3161", _AXIS_STRINGS[0])
    )
    _verify_v2_convention(model)  # must not raise


def test_joint2_shift_changes_shoulder_gravity() -> None:
    """The `+pi/2` joint2 shift materially changes the joint2 gravity term.

    A v1 pose fed as if it were v2 (unshifted) and the WP-2B-01-converted v2 pose give
    different shoulder gravity, which is why the converter is a required upstream of gravity.
    """
    backend = select_backend()
    v1_pose = (0.2, 0.4, -0.3, 0.9, 0.1, -0.2, 0.3)
    v2_pose = JointFrameConverter.v2_default().convert_angles(v1_pose)

    unshifted = backend.tau_grav(v1_pose)
    shifted = backend.tau_grav(v2_pose)
    # joint2 is index 1; the shift lands there and moves its gravity term the most.
    assert abs(shifted[1] - unshifted[1]) > 1.0
