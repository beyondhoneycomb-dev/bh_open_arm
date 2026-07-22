"""Unit tests for single-joint addressing and the step-size vocabulary."""

from __future__ import annotations

import pytest

from backend.jog import (
    STEP_SIZES_DEG,
    Arm,
    JogAddress,
    JogDirection,
    validate_step_size,
)
from backend.jog.addressing import MAX_JOINT_NUMBER, MIN_JOINT_NUMBER
from contracts.action import SINGLE_ARM_ACTION_DIM
from contracts.units import Deg


def test_arm_base_index_is_left_then_right() -> None:
    """Left occupies the first per-arm block; right the second (arm-major order)."""
    assert Arm.LEFT.base_index == 0
    assert Arm.RIGHT.base_index == SINGLE_ARM_ACTION_DIM


@pytest.mark.parametrize(
    ("arm", "joint", "index"),
    [
        (Arm.LEFT, 1, 0),
        (Arm.LEFT, 8, 7),
        (Arm.RIGHT, 1, 8),
        (Arm.RIGHT, 8, 15),
    ],
)
def test_address_resolves_to_bimanual_index(arm: Arm, joint: int, index: int) -> None:
    """An arm-and-joint address maps to its position in the 16-dim vector."""
    assert JogAddress(arm, joint).index == index


@pytest.mark.parametrize("joint", [MIN_JOINT_NUMBER - 1, MAX_JOINT_NUMBER + 1, 0, 9, -1])
def test_address_rejects_out_of_range_joint(joint: int) -> None:
    """A joint number outside the single-arm range is rejected at construction."""
    with pytest.raises(ValueError, match="joint must be in"):
        JogAddress(Arm.LEFT, joint)


def test_direction_signs() -> None:
    """`+` and `−` carry the arithmetic signs the interpolator multiplies by."""
    assert JogDirection.PLUS.value == 1
    assert JogDirection.MINUS.value == -1


@pytest.mark.parametrize("size", STEP_SIZES_DEG)
def test_offered_step_sizes_are_accepted(size: float) -> None:
    """Each offered step size validates and is returned unchanged."""
    assert validate_step_size(Deg(size)) == Deg(size)


def test_offered_step_vocabulary_is_the_spec_minimum() -> None:
    """The offered vocabulary is exactly the FR-MAN-010 minimum set."""
    assert set(STEP_SIZES_DEG) == {0.1, 0.5, 1.0, 5.0}


@pytest.mark.parametrize("size", [2.0, 0.0, 0.2, 10.0, -1.0])
def test_off_vocabulary_step_size_is_rejected(size: float) -> None:
    """A step size outside the offered set is a ValueError, not a silent motion."""
    with pytest.raises(ValueError, match="not one of"):
        validate_step_size(Deg(size))
