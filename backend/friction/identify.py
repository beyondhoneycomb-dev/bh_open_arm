"""The per-joint friction least-squares fit (PG-FRIC-001, spec 04 FR-MAN-035).

Given an excitation log and the inverse-dynamics basis, this fits `Fo + Fv*omega +
Fc*tanh(k_eff*omega)` to each joint's friction residual with `scipy.optimize.least_squares`.
The model is nonlinear in `k_eff` (the tanh slope), so this is a nonlinear least squares, not a
linear regression — a linear fit cannot place the stiction knee.

The fit produces `k_eff`, the true slope; the writer stores `k = k_eff / K_EFF_SCALE` so the
runtime's `k_eff = 0.1 * k` reconstructs it. The v1 seed is the natural warm start: it is the
only prior identification of these joints, so each joint's fit begins from its seed values and
re-identifies for v2.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from backend.friction.basis import DynamicsComponents, InverseDynamicsBasis
from backend.friction.constants import ARM_JOINT_COUNT
from backend.friction.errors import FrictionIdentificationError
from backend.friction.log import ExcitationLog
from backend.friction.model import FrictionParams

# The tanh slope must stay strictly positive; this is its optimiser lower bound. Coulomb and
# viscous coefficients are bounded at zero (a physical friction cannot be negative), while the
# offset is free — it can carry either sign of a small residual bias.
_K_EFF_LOWER = 1.0e-6
_PARAM_LOWER = (-np.inf, 0.0, 0.0, _K_EFF_LOWER)
_PARAM_UPPER = (np.inf, np.inf, np.inf, np.inf)


@dataclass(frozen=True)
class JointFit:
    """One joint's identified friction and the quality of its fit.

    Attributes:
        joint_index: Zero-based arm joint index (0 = joint1).
        params: The identified friction parameters (holding `k_eff`).
        residual_rms_nm: RMS of the post-fit residual — friction residual minus fitted
            friction — over the log, Nm. The friction the model failed to explain.
        converged: Whether `least_squares` reported success.
        n_samples: Number of samples the fit used.
    """

    joint_index: int
    params: FrictionParams
    residual_rms_nm: float
    converged: bool
    n_samples: int


@dataclass(frozen=True)
class IdentificationResult:
    """The whole-arm identification: one fit per joint plus the signals it was derived from.

    Attributes:
        fits: One `JointFit` per arm joint, joint1..joint7 order.
        components: The rigid-body model torque split by contribution (for separation stats).
        friction_residual: `tau - model_total` per sample and joint, the fit target, Nm.
        velocity: The joint velocities the fit ran against, `(n_samples, ARM_JOINT_COUNT)`,
            kept so the separation statistics can re-evaluate the fitted friction at them.
    """

    fits: tuple[JointFit, ...]
    components: DynamicsComponents
    friction_residual: NDArray[np.float64]
    velocity: NDArray[np.float64]

    def params(self) -> tuple[FrictionParams, ...]:
        """Return the identified parameters, joint1..joint7 order."""
        return tuple(fit.params for fit in self.fits)


def _residual(
    theta: NDArray[np.float64], omega: NDArray[np.float64], target: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Return the fit residual `model(omega; theta) - target` for `least_squares`.

    Args:
        theta: The parameter vector `[f_o, f_v, f_c, k_eff]`.
        omega: Joint velocities, rad/s.
        target: The friction residual to fit, Nm.

    Returns:
        (NDArray[np.float64]) Per-sample residual.
    """
    f_o, f_v, f_c, k_eff = theta
    return f_o + f_v * omega + f_c * np.tanh(k_eff * omega) - target


def fit_joint(
    joint_index: int,
    omega: NDArray[np.float64],
    friction_residual: NDArray[np.float64],
    initial: FrictionParams,
) -> JointFit:
    """Fit the tanh friction law to one joint's friction residual.

    Args:
        joint_index: Zero-based arm joint index.
        omega: The joint's velocities over the log, rad/s.
        friction_residual: The joint's friction residual over the log, Nm.
        initial: The warm-start parameters (the v1 seed for this joint).

    Returns:
        (JointFit) The identified parameters and fit quality.

    Raises:
        FrictionIdentificationError: On mismatched or empty input arrays.
    """
    if omega.shape != friction_residual.shape or omega.ndim != 1:
        raise FrictionIdentificationError(
            f"joint {joint_index}: omega {omega.shape} and residual {friction_residual.shape} "
            "must be one-dimensional and equal in length"
        )
    if omega.size == 0:
        raise FrictionIdentificationError(f"joint {joint_index}: cannot fit an empty log")
    x0 = np.array([initial.f_o, initial.f_v, initial.f_c, initial.k_eff], dtype=np.float64)
    solution = least_squares(
        _residual, x0, bounds=(_PARAM_LOWER, _PARAM_UPPER), args=(omega, friction_residual)
    )
    params = FrictionParams(
        f_o=float(solution.x[0]),
        f_v=float(solution.x[1]),
        f_c=float(solution.x[2]),
        k_eff=float(solution.x[3]),
    )
    post_fit = _residual(solution.x, omega, friction_residual)
    rms = float(np.sqrt(np.mean(np.square(post_fit))))
    return JointFit(
        joint_index=joint_index,
        params=params,
        residual_rms_nm=rms,
        converged=bool(solution.success),
        n_samples=int(omega.size),
    )


def identify_friction(
    log: ExcitationLog,
    basis: InverseDynamicsBasis,
    seed: Sequence[FrictionParams],
) -> IdentificationResult:
    """Identify per-joint friction from an excitation log against the inverse-dynamics basis.

    Args:
        log: The excitation log (real from WP-2B-06, or synthetic for the offline demo).
        basis: The inverse-dynamics basis for the same arm.
        seed: The per-joint warm-start parameters (the v1 seed), joint1..joint7 order.

    Returns:
        (IdentificationResult) The per-joint fits and the signals they came from.

    Raises:
        FrictionIdentificationError: If the seed is not `ARM_JOINT_COUNT` long.
    """
    if len(seed) != ARM_JOINT_COUNT:
        raise FrictionIdentificationError(
            f"seed must have {ARM_JOINT_COUNT} entries, got {len(seed)}"
        )
    components = basis.evaluate(log)
    friction_residual = components.friction_residual(log.tau)
    fits = tuple(
        fit_joint(index, log.qd[:, index], friction_residual[:, index], seed[index])
        for index in range(ARM_JOINT_COUNT)
    )
    return IdentificationResult(
        fits=fits,
        components=components,
        friction_residual=friction_residual,
        velocity=np.asarray(log.qd, dtype=np.float64),
    )
