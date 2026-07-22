"""The `Payload` value: a registered mass and centre-of-gravity at the end-effector.

FR-SAF-036/FR-MAN-033 register a payload as a mass plus a centre-of-gravity, both including
the end-effector. This value validates itself on construction so that a mis-registration
(mass outside 0-6.0 kg, or a CoG that is a units/frame error) cannot exist as an object and
therefore cannot reach the gravity model — the point of failing at construction is that an
accepted mis-registration is the FAIL_BLOCKING case this WP exists to prevent.

The CoG is expressed in the end-effector attachment body frame (metres), the frame the
gravity reflection resolves it in; a zero CoG places the whole mass at the mount origin.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from backend.payload.constants import (
    PAYLOAD_COG_MAX_OFFSET_M,
    PAYLOAD_MASS_MAX_KG,
    PAYLOAD_MASS_MIN_KG,
)
from backend.payload.errors import PayloadError

_COG_COMPONENTS = 3


@dataclass(frozen=True)
class Payload:
    """A validated end-effector payload: mass (kg) and CoG (m, attachment-body frame).

    Attributes:
        mass_kg: Total payload mass including the end-effector, in `[0, 6.0]` kg.
        cog_m: Centre-of-gravity offset from the attachment mount, metres, in the
            attachment body frame, as `(x, y, z)`.
        label: A short human identifier for the mounted payload; carries no logic.
    """

    mass_kg: float
    cog_m: tuple[float, float, float]
    label: str

    def __post_init__(self) -> None:
        """Validate the mass band and the CoG, refusing any mis-registration.

        Raises:
            PayloadError: If the mass is outside `[0, 6.0]` kg, or a CoG component is
                non-finite or beyond the units-error sanity ceiling.
        """
        mass = float(self.mass_kg)
        if not math.isfinite(mass) or not PAYLOAD_MASS_MIN_KG <= mass <= PAYLOAD_MASS_MAX_KG:
            raise PayloadError(
                f"payload mass {self.mass_kg} kg is outside the registry band "
                f"[{PAYLOAD_MASS_MIN_KG}, {PAYLOAD_MASS_MAX_KG}] kg (EE included, FR-SAF-036)"
            )
        cog = tuple(float(component) for component in self.cog_m)
        if len(cog) != _COG_COMPONENTS:
            raise PayloadError(f"payload cog_m must have 3 components, got {len(cog)}")
        for axis, component in enumerate(cog):
            if not math.isfinite(component) or abs(component) > PAYLOAD_COG_MAX_OFFSET_M:
                raise PayloadError(
                    f"payload cog_m[{axis}] = {component} m is non-finite or beyond the "
                    f"{PAYLOAD_COG_MAX_OFFSET_M} m units-error sanity ceiling"
                )
        # Freeze the normalised float tuple so downstream math never re-parses the input.
        object.__setattr__(self, "mass_kg", mass)
        object.__setattr__(self, "cog_m", cog)

    @classmethod
    def at_mount(cls, mass_kg: float, label: str) -> Payload:
        """Build a payload whose mass sits at the attachment mount origin (zero CoG offset).

        Args:
            mass_kg: Total payload mass including the end-effector, kg.
            label: A short human identifier.

        Returns:
            (Payload) A validated payload with `cog_m = (0, 0, 0)`.
        """
        return cls(mass_kg=mass_kg, cog_m=(0.0, 0.0, 0.0), label=label)

    @classmethod
    def from_cog(cls, mass_kg: float, cog_m: Sequence[float], label: str) -> Payload:
        """Build a payload from a mass and a CoG sequence, validating both.

        Args:
            mass_kg: Total payload mass including the end-effector, kg.
            cog_m: CoG offset `(x, y, z)` in the attachment body frame, metres.
            label: A short human identifier.

        Returns:
            (Payload) A validated payload.

        Raises:
            PayloadError: If `cog_m` is not three components, or validation fails.
        """
        components = [float(value) for value in cog_m]
        if len(components) != _COG_COMPONENTS:
            raise PayloadError(f"payload cog_m must have 3 components, got {len(components)}")
        return cls(
            mass_kg=mass_kg,
            cog_m=(components[0], components[1], components[2]),
            label=label,
        )
