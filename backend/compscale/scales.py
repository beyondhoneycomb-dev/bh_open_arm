"""The two independent compensation-scale sets: the detection model and the control feedforward.

They are separate frozen types on purpose (FR-SAF-035). `DetectionModelScales` is pinned to the
full 100% model and validates it — the residual observer may only subtract the full dynamics,
so a detection scale other than 1.0 is refused at construction, which is the runtime companion
to the static independence scan in `independence`. `ControlCompensationScales` carries the
provisional v1 partial-compensation coefficients (friction 0.3, Coriolis 0.1) and validates
them to `[0, 1]`. Neither type can be derived from the other: the danger this package exists to
stop is a single knob driving both, so the two never share a field, a constructor, or a default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.compscale.constants import (
    COMP_SCALE_MAX,
    COMP_SCALE_MIN,
    CORIOLIS_COMP_SCALE_DEFAULT,
    DETECTION_MODEL_SCALE,
    FRICTION_COMP_SCALE_DEFAULT,
)
from backend.compscale.errors import ScaleSeparationError


class CompensationScales(Protocol):
    """The read-only friction/Coriolis scale surface the torque computers consume.

    Both concrete scale sets satisfy it structurally; the torque functions take this protocol so
    they never need to know which set they were handed, and so a caller cannot pass a scale set
    that silently lacks one of the two axes.
    """

    @property
    def friction_scale(self) -> float:
        """Fraction of the modelled friction torque to apply."""

    @property
    def coriolis_scale(self) -> float:
        """Fraction of the modelled Coriolis/centrifugal torque to apply."""


@dataclass(frozen=True)
class DetectionModelScales:
    """The residual-observer model scales — the full 100% model, and only that.

    The residual `r = tau_meas - model` estimates external torque only when `model` is the full
    modelled dynamics. This type therefore refuses any scale other than 1.0: it is the structural
    guarantee that the collision detector can never be handed the control feedforward's partial
    coefficient (FR-SAF-035). Build it with `full()` rather than passing scales.
    """

    friction_scale: float = DETECTION_MODEL_SCALE
    coriolis_scale: float = DETECTION_MODEL_SCALE

    def __post_init__(self) -> None:
        """Refuse a detection scale that is not the full model.

        Raises:
            ScaleSeparationError: If either scale is not `DETECTION_MODEL_SCALE` (1.0). A partial
                detection model leaves the un-modelled fraction in the residual as a standing
                offset that dominates the collision threshold floor.
        """
        for name, value in (
            ("friction_scale", self.friction_scale),
            ("coriolis_scale", self.coriolis_scale),
        ):
            if float(value) != DETECTION_MODEL_SCALE:
                raise ScaleSeparationError(
                    f"detection {name} must be the full model {DETECTION_MODEL_SCALE}, "
                    f"got {value} — the residual observer only subtracts the full dynamics"
                )

    @classmethod
    def full(cls) -> DetectionModelScales:
        """Return the 100% detection model — the one configuration this type permits."""
        return cls()


@dataclass(frozen=True)
class ControlCompensationScales:
    """The control-feedforward partial-compensation scales (provisional v1 coefficients).

    Defaults are the v1 partial-compensation coefficients (friction 0.3, Coriolis 0.1), not a
    real `PG-FRIC-001` fit (WP-2B-07, hardware-gated). Each scale is a fraction in `[0, 1]`:
    conservative on purpose, because over-compensating a provisional friction estimate injects
    energy. Independent of `DetectionModelScales` by construction — they share no field.
    """

    friction_scale: float = FRICTION_COMP_SCALE_DEFAULT
    coriolis_scale: float = CORIOLIS_COMP_SCALE_DEFAULT

    def __post_init__(self) -> None:
        """Refuse a control scale outside `[0, 1]`.

        Raises:
            ScaleSeparationError: If either scale is below 0 or above 1. Above 1 over-compensates
                (energy injection); below 0 is nonsensical. Refused rather than clamped.
        """
        for name, value in (
            ("friction_scale", self.friction_scale),
            ("coriolis_scale", self.coriolis_scale),
        ):
            if not COMP_SCALE_MIN <= float(value) <= COMP_SCALE_MAX:
                raise ScaleSeparationError(
                    f"control {name} must be in [{COMP_SCALE_MIN}, {COMP_SCALE_MAX}], got {value}"
                )

    @classmethod
    def partial_comp_v1(cls) -> ControlCompensationScales:
        """Return the provisional v1 partial-compensation default (friction 0.3, Coriolis 0.1)."""
        return cls()
