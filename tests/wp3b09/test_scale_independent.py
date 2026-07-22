"""RUNS ② (CG-3B-09d) — position and rotation scale are independent factors.

`FR-TEL-029`: joint6's ±45° limit forces the rotation channel to be narrowed without
shrinking translation, so `DeltaScaler` must apply `position_scale` and `rotation_scale`
on separate channels. Changing one may not move the other, and each must scale only its
own delta.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch import DeltaScaler
from backend.teleop.clutch.clutch import PoseReference
from backend.teleop.clutch.rotation import quat_angle

_IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])
# A 90-degree rotation about y, as the leader's motion since grip.
_QUARTER_TURN_Y = np.array([0.0, np.sin(np.pi / 4), 0.0, np.cos(np.pi / 4)])
_QUARTER_TURN_ANGLE = np.pi / 2


def _reference_at_origin() -> PoseReference:
    """A reference whose controller and EE both sit at the origin / identity."""
    return PoseReference(
        controller_position=np.zeros(3),
        controller_quaternion=_IDENTITY.copy(),
        ee_position=np.zeros(3),
        ee_quaternion=_IDENTITY.copy(),
    )


def test_position_scales_only_translation() -> None:
    """Target translation is `position_scale x` the controller delta; rotation untouched."""
    reference = _reference_at_origin()
    controller_delta = np.array([0.2, -0.4, 0.6])

    scaler = DeltaScaler(position_scale=0.5, rotation_scale=1.0)
    target = scaler.target(reference, controller_delta, _IDENTITY)

    assert np.allclose(target.position, 0.5 * controller_delta)
    assert quat_angle(target.quaternion) < 1e-9  # identity rotation delta stays identity


def test_rotation_scales_only_orientation() -> None:
    """Target rotation angle is `rotation_scale x` the controller angle; position untouched."""
    reference = _reference_at_origin()

    scaler = DeltaScaler(position_scale=1.0, rotation_scale=0.5)
    target = scaler.target(reference, np.zeros(3), _QUARTER_TURN_Y)

    assert np.allclose(target.position, np.zeros(3))  # no translation delta
    assert np.isclose(quat_angle(target.quaternion), 0.5 * _QUARTER_TURN_ANGLE)


def test_changing_rotation_scale_leaves_position_identical() -> None:
    """Two scalers differing only in rotation scale produce the same target position."""
    reference = _reference_at_origin()
    controller_delta = np.array([0.3, 0.1, -0.2])

    low_rotation = DeltaScaler(position_scale=0.8, rotation_scale=0.25)
    high_rotation = DeltaScaler(position_scale=0.8, rotation_scale=1.0)

    low = low_rotation.target(reference, controller_delta, _QUARTER_TURN_Y)
    high = high_rotation.target(reference, controller_delta, _QUARTER_TURN_Y)

    assert np.allclose(low.position, high.position)  # position independent of rotation scale
    assert quat_angle(low.quaternion) < quat_angle(high.quaternion)  # rotation did change


def test_changing_position_scale_leaves_rotation_identical() -> None:
    """Two scalers differing only in position scale produce the same target rotation."""
    reference = _reference_at_origin()
    controller_delta = np.array([0.3, 0.1, -0.2])

    near = DeltaScaler(position_scale=0.2, rotation_scale=1.0)
    far = DeltaScaler(position_scale=1.5, rotation_scale=1.0)

    near_target = near.target(reference, controller_delta, _QUARTER_TURN_Y)
    far_target = far.target(reference, controller_delta, _QUARTER_TURN_Y)

    assert np.isclose(quat_angle(near_target.quaternion), quat_angle(far_target.quaternion))
    assert not np.allclose(near_target.position, far_target.position)  # position did change
