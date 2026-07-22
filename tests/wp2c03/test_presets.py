"""Sensitivity presets scale a calibrated base and re-bound it (WP-2C-03, `12` FR-SAF-063).

`12` FR-SAF-063 bundles a threshold scale, an observer gain and a confirm-sample count under
one control, and requires the effective per-joint threshold shown in Nm. These tests hold
that the scale moves the threshold in the sensitivity direction, that the ten-LSB floor still
binds after scaling so a HIGH preset cannot push a joint below noise, and that the gain and
confirm values ride through as the bundle.
"""

from __future__ import annotations

import pytest

from backend.safety_bringup.constants import ARM_JOINT_COUNT
from backend.safety_bringup.thresholds import floor_for_joint
from backend.threshold_calib import (
    SENSITIVITY_PRESETS,
    PresetError,
    apply_preset,
)

_BASE_NM = (2.0, 2.0, 1.5, 1.5, 0.5, 0.5, 0.5)


def test_high_is_more_sensitive_than_low() -> None:
    # HIGH lowers the effective threshold below MEDIUM below LOW, joint by joint.
    low = apply_preset(_BASE_NM, "LOW").effective_nm()
    medium = apply_preset(_BASE_NM, "MEDIUM").effective_nm()
    high = apply_preset(_BASE_NM, "HIGH").effective_nm()
    for joint in range(ARM_JOINT_COUNT):
        assert high[joint] < medium[joint] < low[joint]


def test_medium_is_unity_scale() -> None:
    application = apply_preset(_BASE_NM, "MEDIUM")
    assert application.preset.threshold_scale == 1.0
    for joint in application.per_joint:
        assert joint.effective_nm == pytest.approx(joint.base_nm)


def test_preset_carries_gain_and_confirm_bundle() -> None:
    application = apply_preset(_BASE_NM, "HIGH")
    expected = SENSITIVITY_PRESETS["HIGH"]
    assert application.preset.observer_gain == expected.observer_gain
    assert application.preset.confirm_samples == expected.confirm_samples


def test_scaled_below_floor_is_raised_to_floor() -> None:
    # A HIGH scale on a wrist joint whose base is already tiny still cannot go below floor.
    tiny_base = (0.05,) * ARM_JOINT_COUNT
    application = apply_preset(tiny_base, "HIGH")
    for joint in application.per_joint:
        floor = floor_for_joint(joint.joint_index)
        assert joint.effective_nm >= floor
        if 0.05 * SENSITIVITY_PRESETS["HIGH"].threshold_scale < floor:
            assert joint.floor_clamped
            assert joint.effective_nm == pytest.approx(floor)


def test_unknown_preset_is_refused() -> None:
    with pytest.raises(PresetError, match="unknown sensitivity preset"):
        apply_preset(_BASE_NM, "PARANOID")
