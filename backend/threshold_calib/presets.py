"""Sensitivity presets over a calibrated base threshold (WP-2C-03, `12` FR-SAF-063).

A preset bundles a threshold scale, an observer gain and a confirm-sample count so one
control adjusts all three (`12` FR-SAF-063). This module applies the scale to a calibrated
base and shows the resulting effective per-joint threshold in Nm — the display the
requirement mandates. The scaled threshold is re-bounded by the same physics floor and
effort cap as the base proposal: a HIGH-sensitivity scale must not push a joint below its
ten-LSB noise floor, so the preset cannot defeat `12` FR-SAF-019 by another route.

The confirm-sample count is carried through as data. The debounce that consumes it —
consecutive-over-threshold confirmation and hysteresis — is WP-2C-04's frozen contract, and
re-implementing it here would create a second detection path.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.safety_bringup.constants import URDF_EFFORT_LIMIT_NM
from backend.safety_bringup.thresholds import floor_for_joint
from backend.threshold_calib.constants import SENSITIVITY_PRESETS, SensitivityPreset


class PresetError(Exception):
    """Raised when an unknown preset name is requested."""


@dataclass(frozen=True)
class EffectiveThreshold:
    """One joint's effective threshold after a preset scale, bounded by physics.

    Attributes:
        joint_index: Zero-based arm joint index (0 == J1).
        base_nm: The calibrated base threshold the preset scaled, Nm.
        effective_nm: The scaled threshold after the floor and effort cap, Nm.
        floor_clamped: True when the scaled value sat below the floor and was raised to it.
        effort_capped: True when the scaled value exceeded effort and was lowered to it.
    """

    joint_index: int
    base_nm: float
    effective_nm: float
    floor_clamped: bool
    effort_capped: bool


@dataclass(frozen=True)
class PresetApplication:
    """The full result of applying a sensitivity preset to a calibrated base.

    Attributes:
        preset: The preset that was applied, carrying its gain and confirm-sample values.
        per_joint: One `EffectiveThreshold` per joint, in joint order.
    """

    preset: SensitivityPreset
    per_joint: tuple[EffectiveThreshold, ...]

    def effective_nm(self) -> tuple[float, ...]:
        """Return the per-joint effective thresholds after the preset, Nm.

        Returns:
            (tuple[float, ...]) The bounded post-preset thresholds in joint order.
        """
        return tuple(joint.effective_nm for joint in self.per_joint)


def apply_preset(base_nm: tuple[float, ...], preset_name: str) -> PresetApplication:
    """Scale a calibrated base by a sensitivity preset and re-bound each joint.

    Args:
        base_nm: The calibrated per-joint base thresholds, Nm, in joint order.
        preset_name: One of the `SENSITIVITY_PRESETS` keys (`LOW`/`MEDIUM`/`HIGH`).

    Returns:
        (PresetApplication) The preset and the bounded per-joint effective thresholds.

    Raises:
        PresetError: If the preset name is not a defined sensitivity preset.
    """
    preset = SENSITIVITY_PRESETS.get(preset_name)
    if preset is None:
        raise PresetError(
            f"unknown sensitivity preset {preset_name!r}; "
            f"expected one of {sorted(SENSITIVITY_PRESETS)}"
        )
    per_joint = tuple(
        _scaled(index, base, preset.threshold_scale) for index, base in enumerate(base_nm)
    )
    return PresetApplication(preset=preset, per_joint=per_joint)


def _scaled(joint_index: int, base_nm: float, scale: float) -> EffectiveThreshold:
    """Apply a preset scale to one base threshold and re-bound it by physics.

    Args:
        joint_index: Zero-based arm joint index.
        base_nm: The calibrated base threshold, Nm.
        scale: The preset's threshold scale.

    Returns:
        (EffectiveThreshold) The scaled, floor- and cap-bounded threshold with its flags.
    """
    floor = floor_for_joint(joint_index)
    cap = URDF_EFFORT_LIMIT_NM[joint_index]
    scaled = base_nm * scale
    effective = min(max(scaled, floor), cap)
    return EffectiveThreshold(
        joint_index=joint_index,
        base_nm=base_nm,
        effective_nm=effective,
        floor_clamped=scaled < floor,
        effort_capped=scaled > cap,
    )
