"""Axis-sign normalisation — a v1 joint whose positive rotation opposes the v2 reference is flipped.

FR-SAF-033 requires normalising a v1 model's axis signs onto the v2 `joint_axes.yaml` reference,
alongside the joint2 zero shift. A converter built with an explicit per-joint sign vector flips
the angle, velocity, and torque of every joint marked -1; positions still also carry the joint2
zero offset, while velocities and torques carry the sign alone.
"""

from __future__ import annotations

import math

import pytest

from backend.dynamics.constants import ARM_JOINT_COUNT, V2_JOINT_AXES
from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.errors import DynamicsConversionError

# joints 3 and 5 (zero-based 2 and 4) declared opposite to the v2 reference.
FLIPPED_SIGNS = (1, 1, -1, 1, -1, 1, 1)


def test_reference_axes_have_one_entry_per_joint() -> None:
    """The v2 reference axis table covers all seven arm joints as unit vectors."""
    assert len(V2_JOINT_AXES) == ARM_JOINT_COUNT
    for axis in V2_JOINT_AXES:
        assert math.isclose(math.sqrt(sum(component**2 for component in axis)), 1.0)


def test_flipped_joints_negate_torque() -> None:
    """Torque flips sign on the joints marked -1 and passes through on the rest (no offset)."""
    converter = JointFrameConverter(axis_signs=FLIPPED_SIGNS)
    out = converter.convert_torques([1.0] * ARM_JOINT_COUNT)
    assert out == pytest.approx([1.0, 1.0, -1.0, 1.0, -1.0, 1.0, 1.0])


def test_flipped_joints_negate_velocity() -> None:
    """Velocity flips on the marked joints with no zero offset applied."""
    converter = JointFrameConverter(axis_signs=FLIPPED_SIGNS)
    out = converter.convert_velocities([2.0] * ARM_JOINT_COUNT)
    assert out == pytest.approx([2.0, 2.0, -2.0, 2.0, -2.0, 2.0, 2.0])


def test_flipped_angle_carries_both_sign_and_joint2_offset() -> None:
    """A flipped angle negates, and joint2 still receives the +pi/2 zero shift on top."""
    converter = JointFrameConverter(axis_signs=FLIPPED_SIGNS)
    out = converter.convert_angles([0.5] * ARM_JOINT_COUNT)
    assert out[2] == pytest.approx(-0.5)
    assert out[4] == pytest.approx(-0.5)
    assert out[1] == pytest.approx(0.5 + math.pi / 2.0)
    assert out[0] == pytest.approx(0.5)


def test_flipped_angle_round_trips() -> None:
    """Invert undoes convert even with flips, so the v1 argument is recovered exactly."""
    converter = JointFrameConverter(axis_signs=FLIPPED_SIGNS)
    v1 = [0.1, -1.2, 0.3, 0.7, -0.4, 0.2, -0.9]
    assert converter.invert_angles(converter.convert_angles(v1)) == pytest.approx(v1)


def test_non_unit_sign_is_refused() -> None:
    """A sign vector entry that is not +/-1 is refused — signs are unit flips only."""
    with pytest.raises(DynamicsConversionError, match="must be [+]1 or -1"):
        JointFrameConverter(axis_signs=(1, 1, 2, 1, 1, 1, 1))


def test_wrong_width_sign_vector_is_refused() -> None:
    """A sign vector that is not seven wide is refused."""
    with pytest.raises(DynamicsConversionError, match="must have 7 entries"):
        JointFrameConverter(axis_signs=(1, 1, 1))
