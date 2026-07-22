"""The four-term tanh friction law and its per-joint parameters (spec 04 FR-MAN-034).

`tau_fric(omega) = Fo + Fv*omega + Fc*tanh(k_eff*omega)`. This module owns the model function
and the parameter record; the fitter (`identify`) produces the record and the writer
(`writer`) serialises it. The record stores `k_eff` — the true tanh slope — and exposes the
YAML `k` as a derived property, because the runtime applies `k_eff = 0.1 * k` and storing the
raw slope as `k` would deploy a friction ten times too soft in the stiction knee (constants
`K_EFF_SCALE`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.friction.constants import K_EFF_SCALE
from backend.friction.errors import FrictionIdentificationError


@dataclass(frozen=True)
class FrictionParams:
    """One joint's tanh friction parameters, holding the effective slope `k_eff`.

    Attributes:
        f_o: Constant offset torque, Nm — the `Fo` term.
        f_v: Viscous coefficient, Nm per rad/s — the `Fv` term.
        f_c: Coulomb amplitude, Nm — the `Fc` term.
        k_eff: The effective tanh slope actually applied, s/rad. The YAML `k` is
            `k_eff / K_EFF_SCALE`; the runtime multiplies that `k` by 0.1 to recover `k_eff`.
    """

    f_o: float
    f_v: float
    f_c: float
    k_eff: float

    def __post_init__(self) -> None:
        """Refuse a non-positive tanh slope, which has no stiction knee to identify.

        Raises:
            FrictionIdentificationError: If `k_eff` is not strictly positive.
        """
        if not self.k_eff > 0.0:
            raise FrictionIdentificationError(
                f"k_eff must be strictly positive (a tanh slope), got {self.k_eff}"
            )

    @property
    def k(self) -> float:
        """The YAML-stored slope `k = k_eff / K_EFF_SCALE`, so runtime `0.1 * k` reconstructs it."""
        return self.k_eff / K_EFF_SCALE

    @classmethod
    def from_stored_k(cls, f_o: float, f_v: float, f_c: float, k: float) -> FrictionParams:
        """Build parameters from a YAML `k`, applying the `k_eff = 0.1 * k` runtime convention.

        Args:
            f_o: The `Fo` term, Nm.
            f_v: The `Fv` term, Nm per rad/s.
            f_c: The `Fc` term, Nm.
            k: The stored slope as it appears in a friction.yaml file.

        Returns:
            (FrictionParams) Parameters whose `k_eff` is `K_EFF_SCALE * k`.
        """
        return cls(f_o=f_o, f_v=f_v, f_c=f_c, k_eff=K_EFF_SCALE * k)

    def tau(self, omega: NDArray[np.float64]) -> NDArray[np.float64]:
        """Evaluate the friction torque at each velocity in `omega`.

        Args:
            omega: Joint velocities, rad/s.

        Returns:
            (NDArray[np.float64]) Friction torque at each velocity, Nm.
        """
        speeds = np.asarray(omega, dtype=np.float64)
        return self.f_o + self.f_v * speeds + self.f_c * np.tanh(self.k_eff * speeds)
