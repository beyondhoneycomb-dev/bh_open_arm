"""The observer's model terms, composed from reused primitives — the single reuse point.

The momentum observer needs four model quantities per step. Three are reused, one is added here:

  * `p = M(q)*q_dot`  — the generalized momentum, from `MassMatrix` (this package; no reused
    module exposes the inertia).
  * `g_hat(q)`        — gravity, from `backend.gravity` (WP-2B-02).
  * `C_hat^T*q_dot`   — the Coriolis term, from `backend.gravity.tau_coriolis` (WP-2B-02).
  * `F_hat(q_dot)`    — friction, from `backend.friction` via `FrictionFeedforward` (WP-2B-07).

Modeling note on the Coriolis term. The momentum observer's identity `M_dot = C + C^T` makes the
exact term `C^T*q_dot`, while `backend.gravity.tau_coriolis` returns mujoco's Coriolis vector
`C*q_dot` (the bias force minus gravity). WP-2C-01 reuses that primitive as the `C_hat^T*q_dot`
slot rather than opening a second dynamics source: the difference `(C^T - C)*q_dot` is a
velocity-dependent residual bias that the torque-ON threshold calibration (WP-2C-03) absorbs, and
which the model-error monitor (WP-2C-09) watches — both deferred to hardware. The offline
acceptance drives plant and observer through this same term, so isolation is exact there and the
term's hardware fidelity is the deferred calibration, not this package's claim.

The `beta` helper is the observer integrand's model part, `tau_meas + C_hat^T*q_dot - g_hat -
F_hat`; keeping it here means the observer never re-derives which sign each reused term carries.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from backend.friction import FrictionParams
from backend.gmo.friction_term import FrictionFeedforward
from backend.gmo.mass import MassMatrix
from backend.gravity import MuJoCoV2GravityBackend
from backend.gravity.backend import Arm


class GmoModelTerms:
    """The reused gravity/Coriolis/friction model plus the added inertia, for one arm."""

    def __init__(
        self,
        arm: Arm = Arm.RIGHT,
        friction: FrictionFeedforward | None = None,
    ) -> None:
        """Build the arm's model terms, reusing WP-2B-02 gravity and WP-2B-07 friction.

        Args:
            arm: Which follower arm the observer runs on.
            friction: The friction feed-forward, or None to use the v1-seed default. A real run
                passes a `FrictionFeedforward` built from the identified `friction.yaml` set.
        """
        self._mass = MassMatrix(arm)
        # The gravity backend at full modelled gravity: the observer's g_hat is the model, not a
        # payload-trimmed value, so gravity_scale is left at its 1.0 default.
        self._gravity = MuJoCoV2GravityBackend(arm)
        self._friction = friction if friction is not None else FrictionFeedforward()

    @property
    def arm(self) -> Arm:
        """The arm these terms compute for."""
        return self._gravity.arm

    @classmethod
    def from_friction_params(
        cls, params: Sequence[FrictionParams], arm: Arm = Arm.RIGHT
    ) -> GmoModelTerms:
        """Build model terms from an explicit per-joint friction set (e.g. the identified fit)."""
        return cls(arm=arm, friction=FrictionFeedforward(params))

    def momentum(self, q: Sequence[float], qdot: Sequence[float]) -> NDArray[np.float64]:
        """Return the generalized momentum `p = M(q)*q_dot`, Nm*s."""
        return self._mass.momentum(q, qdot)

    def gravity(self, q: Sequence[float]) -> NDArray[np.float64]:
        """Return the gravity term `g_hat(q)`, Nm (reused WP-2B-02)."""
        return np.asarray(self._gravity.tau_grav(q), dtype=np.float64)

    def coriolis(self, q: Sequence[float], qdot: Sequence[float]) -> NDArray[np.float64]:
        """Return the Coriolis term used as `C_hat^T*q_dot`, Nm (reused WP-2B-02)."""
        return np.asarray(self._gravity.tau_coriolis(q, qdot), dtype=np.float64)

    def friction(self, qdot: Sequence[float]) -> NDArray[np.float64]:
        """Return the friction term `F_hat(q_dot)`, Nm (reused WP-2B-07)."""
        return self._friction.friction(qdot)

    def beta(
        self,
        q: Sequence[float],
        qdot: Sequence[float],
        tau_meas: Sequence[float],
    ) -> NDArray[np.float64]:
        """Return the observer integrand's model part `tau_meas + C_hat^T*q_dot - g_hat - F_hat`.

        This is everything the momentum derivative equals except the residual feedback and the
        unmodelled external torque; the observer integrates `beta + r` and reads the gap as `r`.

        Args:
            q: Joint angles, v2 convention, radians.
            qdot: Joint velocities, rad/s.
            tau_meas: Measured joint torque, Nm — present only when `use_velocity_and_torque`.

        Returns:
            (NDArray[np.float64]) Per-joint integrand model part, Nm, joint1..joint7 order.
        """
        torque = np.asarray(tau_meas, dtype=np.float64)
        return torque + self.coriolis(q, qdot) - self.gravity(q) - self.friction(qdot)
