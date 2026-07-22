"""The generalized-momentum-observer residual `r(t)` with per-joint independent gain.

WP-2C-01's frozen output:

    r(t) = K { p - integral( tau + C_hat^T*q_dot - g_hat - F_hat + r ) dxi - p(0) }

`r` is a per-joint estimate of the unmodelled joint torque; on a collision that unmodelled torque
is the external contact wrench mapped to joints, so a nonzero `r_i` isolates joint i. The gain `K`
is a per-joint diagonal, so each joint's residual has its own first-order bandwidth
(`r_dot = K*(tau_ext - r)`) — acceptance ③.

Discretisation. This integrates forward-Euler, causally: at step n the residual reads the integral
accumulated strictly before n, then the accumulator advances by `(beta_n + r_n)*dt`. The residual
starts at exactly zero (`r_0 = K*(p_0 - 0 - p_0) = 0`) and there is no algebraic loop, because
`r_n` depends only on past accumulation.

Ownership/threading: the observer holds mutable integrator state and its model terms hold private
mujoco buffers, so one observer is driven from one thread — the actuation loop that owns the CAN
bus and hands it `(q, q_dot, tau_meas)` each tick. It never reads the bus itself (see
`single_process`).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from backend.gmo.constants import DEFAULT_OBSERVER_GAIN, GMO_JOINT_COUNT, OBSERVER_GAIN_MIN
from backend.gmo.errors import GmoJointCountError, ObserverConfigError
from backend.gmo.model import GmoModelTerms


class MomentumObserver:
    """The momentum-observer residual for one arm, with a per-joint gain and integrator state."""

    def __init__(
        self,
        model: GmoModelTerms,
        gain: Sequence[float] | float = DEFAULT_OBSERVER_GAIN,
    ) -> None:
        """Build the observer over its model terms and validate the per-joint gain.

        Args:
            model: The reused gravity/Coriolis/friction plus inertia terms for this arm.
            gain: The residual-loop gain `K`. A scalar applies uniformly; a sequence sets each
                joint independently. Every entry must be strictly positive.

        Raises:
            ObserverConfigError: If a gain entry is not strictly positive, or a gain sequence is
                not `GMO_JOINT_COUNT` wide.
        """
        self._model = model
        self._gain = self._checked_gain(gain)
        self._integral: NDArray[np.float64] = np.zeros(GMO_JOINT_COUNT, dtype=np.float64)
        self._p0: NDArray[np.float64] = np.zeros(GMO_JOINT_COUNT, dtype=np.float64)
        self._initialized = False

    @property
    def gain(self) -> NDArray[np.float64]:
        """The per-joint residual-loop gain `K`, joint1..joint7 order."""
        return self._gain.copy()

    @property
    def model(self) -> GmoModelTerms:
        """The observer's reused model terms."""
        return self._model

    def reset(self, q: Sequence[float], qdot: Sequence[float]) -> None:
        """Seed the observer's initial momentum `p(0)` and zero its integrator.

        Call at activation, from the rest state the arm is holding, so the residual starts at zero
        and rises only as unmodelled torque appears.

        Args:
            q: Joint angles at activation, v2 convention, radians.
            qdot: Joint velocities at activation, rad/s.
        """
        self._p0 = self._model.momentum(q, qdot)
        self._integral = np.zeros(GMO_JOINT_COUNT, dtype=np.float64)
        self._initialized = True

    def update(
        self,
        q: Sequence[float],
        qdot: Sequence[float],
        tau_meas: Sequence[float],
        dt: float,
    ) -> NDArray[np.float64]:
        """Advance one tick and return the per-joint residual `r`.

        The first call seeds `p(0)` from `(q, q_dot)` if `reset` was not called, so a residual of
        zero on the first tick is guaranteed rather than a spurious transient.

        Args:
            q: Joint angles this tick, v2 convention, radians.
            qdot: Joint velocities this tick, rad/s.
            tau_meas: Measured joint torque this tick, Nm.
            dt: The tick period, s. Must be strictly positive.

        Returns:
            (NDArray[np.float64]) Per-joint residual `r`, Nm, joint1..joint7 order.

        Raises:
            ObserverConfigError: If `dt` is not strictly positive.
            GmoJointCountError: On any joint vector of the wrong width.
        """
        if not dt > 0.0:
            raise ObserverConfigError(f"dt must be strictly positive, got {dt}")
        if not self._initialized:
            self.reset(q, qdot)
        momentum = self._model.momentum(q, qdot)
        self._checked_width(momentum)
        residual = self._gain * (momentum - self._integral - self._p0)
        beta = self._model.beta(q, qdot, tau_meas)
        self._checked_width(beta)
        self._integral = self._integral + (beta + residual) * dt
        return residual

    def _checked_gain(self, gain: Sequence[float] | float) -> NDArray[np.float64]:
        """Return the gain as a strictly-positive length-`GMO_JOINT_COUNT` vector.

        Raises:
            ObserverConfigError: On a non-positive entry or a wrong-width sequence.
        """
        vector: NDArray[np.float64]
        if isinstance(gain, int | float):
            vector = np.full(GMO_JOINT_COUNT, float(gain), dtype=np.float64)
        else:
            vector = np.asarray(gain, dtype=np.float64)
        if vector.shape != (GMO_JOINT_COUNT,):
            raise ObserverConfigError(
                f"gain must have {GMO_JOINT_COUNT} entries, got shape {vector.shape}"
            )
        if not np.all(vector > OBSERVER_GAIN_MIN):
            raise ObserverConfigError(
                f"every observer gain must be strictly positive (> {OBSERVER_GAIN_MIN}), got "
                f"{vector.tolist()}"
            )
        return vector

    def _checked_width(self, vector: NDArray[np.float64]) -> None:
        """Refuse a per-joint model vector that is not `GMO_JOINT_COUNT` wide.

        Raises:
            GmoJointCountError: If the model returned a vector of the wrong width.
        """
        if vector.shape != (GMO_JOINT_COUNT,):
            raise GmoJointCountError(
                f"model term must have {GMO_JOINT_COUNT} entries, got shape {vector.shape}"
            )
