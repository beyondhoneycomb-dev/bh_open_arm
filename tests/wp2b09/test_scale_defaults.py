"""The two scale sets carry the declared defaults and validate their own ranges.

WP-2B-09 acceptance: control compensation defaults to the provisional v1 partial coefficients
(friction 0.3, Coriolis 0.1) and the detection model is the full 100% model. The defaults are a
frozen part of the contract, so they are asserted as exact values here.
"""

from __future__ import annotations

import pytest

from backend.compscale import (
    CORIOLIS_COMP_SCALE_DEFAULT,
    DETECTION_MODEL_SCALE,
    FRICTION_COMP_SCALE_DEFAULT,
    ControlCompensationScales,
    DetectionModelScales,
    ScaleSeparationError,
)


def test_control_defaults_are_v1_partial_comp() -> None:
    """Control compensation defaults to friction 0.3 / Coriolis 0.1 (v1 partial-comp)."""
    scales = ControlCompensationScales()
    assert scales.friction_scale == FRICTION_COMP_SCALE_DEFAULT == 0.3
    assert scales.coriolis_scale == CORIOLIS_COMP_SCALE_DEFAULT == 0.1


def test_partial_comp_v1_builder_matches_default() -> None:
    """`partial_comp_v1()` is the same as the default construction."""
    assert ControlCompensationScales.partial_comp_v1() == ControlCompensationScales()


def test_detection_default_is_full_model() -> None:
    """The detection model scale is 100% on both axes."""
    scales = DetectionModelScales.full()
    assert scales.friction_scale == DETECTION_MODEL_SCALE == 1.0
    assert scales.coriolis_scale == DETECTION_MODEL_SCALE == 1.0


def test_control_scale_is_configurable_and_independent() -> None:
    """Control scales can be set independently of the detection model's 100%."""
    scales = ControlCompensationScales(friction_scale=0.5, coriolis_scale=0.0)
    assert scales.friction_scale == 0.5
    assert scales.coriolis_scale == 0.0
    assert DetectionModelScales.full().friction_scale == 1.0


@pytest.mark.parametrize("bad_value", [-0.1, 1.1, 2.0])
def test_control_scale_outside_unit_band_is_refused(bad_value: float) -> None:
    """A control scale below 0 or above 1 is refused, not clamped."""
    with pytest.raises(ScaleSeparationError):
        ControlCompensationScales(friction_scale=bad_value)
    with pytest.raises(ScaleSeparationError):
        ControlCompensationScales(coriolis_scale=bad_value)


def test_control_scale_band_endpoints_are_allowed() -> None:
    """The unit-band endpoints 0 and 1 are valid control scales."""
    assert ControlCompensationScales(friction_scale=0.0, coriolis_scale=1.0).friction_scale == 0.0
