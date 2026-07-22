"""Acceptance (1) — feeding a v1 joint2 angle applies the +pi/2 shift.

This is the FAIL_BLOCKING invariant of B-2B.0: without the shift, a v1 gravity model fed at
v2 angles swaps sin<->cos at the shoulder (joint2) and the residual detector mis-fires forever
(spec 12 §2.6). The shift is exact — the v1 joint2 range maps onto the v2 range under +pi/2.
"""

from __future__ import annotations

import math

import pytest

from backend.dynamics.constants import (
    ARM_JOINT_COUNT,
    J2_ZERO_SHIFT_RAD,
    JOINT2_INDEX,
    V1_JOINT2_RANGE_RAD,
    V2_JOINT2_RANGE_RAD,
)
from backend.dynamics.converter import JointFrameConverter, convert_joint2_angle

# The v1/v2 range endpoints are quoted to five places in the spec, so the exact +pi/2 image
# lands within a few micro-radians of them, not on them.
RANGE_TOLERANCE_RAD = 1e-4


def test_shift_constant_is_half_pi() -> None:
    """The joint2 shift is exactly pi/2 (the spec's +1.570796 rad rounded to six places)."""
    assert math.pi / 2.0 == J2_ZERO_SHIFT_RAD
    assert round(J2_ZERO_SHIFT_RAD, 6) == 1.570796


def test_v1_joint2_lower_maps_to_v2_lower() -> None:
    """The v1 joint2 lower limit shifts onto the v2 lower limit."""
    shifted = convert_joint2_angle(V1_JOINT2_RANGE_RAD[0])
    assert shifted == pytest.approx(V2_JOINT2_RANGE_RAD[0], abs=RANGE_TOLERANCE_RAD)


def test_v1_joint2_upper_maps_to_v2_upper() -> None:
    """The v1 joint2 upper limit shifts onto the v2 upper limit."""
    shifted = convert_joint2_angle(V1_JOINT2_RANGE_RAD[1])
    assert shifted == pytest.approx(V2_JOINT2_RANGE_RAD[1], abs=RANGE_TOLERANCE_RAD)


def test_convert_angles_shifts_only_joint2(default_converter: JointFrameConverter) -> None:
    """A full-vector convert adds pi/2 at joint2 and leaves the other six joints untouched."""
    v2 = default_converter.convert_angles([0.0] * ARM_JOINT_COUNT)
    assert v2[JOINT2_INDEX] == pytest.approx(math.pi / 2.0)
    for index in range(ARM_JOINT_COUNT):
        if index != JOINT2_INDEX:
            assert v2[index] == pytest.approx(0.0)


def test_convert_then_invert_is_identity(default_converter: JointFrameConverter) -> None:
    """`invert_angles` undoes `convert_angles` so a v1 model is evaluated at the right argument."""
    v1 = [0.1, -1.2, 0.3, 0.7, -0.4, 0.2, -0.9]
    round_trip = default_converter.invert_angles(default_converter.convert_angles(v1))
    assert round_trip == pytest.approx(v1)


def test_wrong_width_vector_is_refused(default_converter: JointFrameConverter) -> None:
    """A joint vector that is not seven wide is refused rather than silently truncated."""
    from backend.dynamics.errors import DynamicsConversionError

    with pytest.raises(DynamicsConversionError):
        default_converter.convert_angles([0.0] * (ARM_JOINT_COUNT - 1))
