"""The detection model is structurally pinned to 100% and cannot be handed a partial scale.

This is the runtime companion to the static independence scan: even if some caller tries to build
a detection model from the control coefficient, construction refuses it. A partial detection model
leaves the un-modelled fraction in the residual as a standing offset (FR-SAF-035).
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.compscale import (
    FRICTION_COMP_SCALE_DEFAULT,
    ControlCompensationScales,
    DetectionModelScales,
    ScaleSeparationError,
)


def test_detection_refuses_control_friction_coefficient() -> None:
    """Building a detection model with the control friction coefficient (0.3) is refused."""
    with pytest.raises(ScaleSeparationError):
        DetectionModelScales(friction_scale=FRICTION_COMP_SCALE_DEFAULT)


@pytest.mark.parametrize("bad_value", [0.0, 0.1, 0.3, 0.99, 1.2])
def test_detection_refuses_any_non_full_scale(bad_value: float) -> None:
    """Any detection scale other than 1.0 is refused on either axis."""
    with pytest.raises(ScaleSeparationError):
        DetectionModelScales(friction_scale=bad_value)
    with pytest.raises(ScaleSeparationError):
        DetectionModelScales(coriolis_scale=bad_value)


def test_detection_scales_are_frozen() -> None:
    """A detection scale field cannot be reassigned after construction."""
    scales = DetectionModelScales.full()
    with pytest.raises(dataclasses.FrozenInstanceError):
        scales.friction_scale = 0.3  # type: ignore[misc]


def test_control_and_detection_are_distinct_types() -> None:
    """The two scale sets are separate types, so one cannot stand in for the other."""
    control = ControlCompensationScales()
    assert not isinstance(control, DetectionModelScales)
    assert type(control).__name__ != DetectionModelScales.__name__
