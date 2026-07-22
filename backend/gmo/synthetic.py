"""Synthetic external-force injection for the offline observer acceptance (WP-2C-01 ①).

This host has no arm, so the residual is exercised against a synthetic plant. The plant is made
*consistent with the observer's own model*: it drives a chosen joint trajectory through the same
`GmoModelTerms` the observer uses, forms the true momentum `p_n = M(q_n)*q_dot_n`, and back-solves
the measured torque `tau_meas` from the discrete momentum balance the observer inverts:

    p_dot_n := (p_{n+1} - p_n) / dt
    tau_meas_n := p_dot_n - C_hat^T*q_dot_n + g_hat_n + F_hat_n - tau_ext_n

Feeding that `tau_meas` back through the observer telescopes exactly: the residual `r` tracks the
injected `tau_ext` with the first-order response `r_dot = K*(tau_ext - r)`, and stays at zero on
every joint the injection did not touch. That is the machinery proof — integration, per-joint
gain, isolation. It is *not* a claim that this model matches hardware: on the real arm the model
mismatch is a residual bias the torque-ON threshold calibration (WP-2C-03) absorbs, which this
consistent-plant harness deliberately does not carry. Passing a friction set to the model that
differs from the plant's is how a test can add that mismatch back in on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.gmo.constants import GMO_JOINT_COUNT, NOMINAL_DETECTION_DT_S
from backend.gmo.errors import GmoJointCountError
from backend.gmo.model import GmoModelTerms

# Arbitrary per-joint excitation for the offline demo: distinct frequencies so the mass matrix and
# Coriolis term actually vary across joints and time, small amplitudes and near-zero offsets so the
# trajectory stays well inside the v2 joint ranges. These are test-signal parameters, not any
# safety or model quantity.
_TRAJECTORY_AMPLITUDE_RAD = 0.15
_TRAJECTORY_OFFSETS_RAD = (0.0, 0.30, 0.0, 0.40, 0.0, 0.0, 0.0)
_TRAJECTORY_OMEGAS_RAD_S = (1.0, 1.3, 1.7, 2.1, 2.5, 2.9, 3.3)


@dataclass(frozen=True)
class SyntheticInjection:
    """One synthetic run: the signals the observer consumes plus the ground-truth injection.

    Attributes:
        q: Joint angles per step, `(n_steps, 7)`, radians.
        qdot: Joint velocities per step, `(n_steps, 7)`, rad/s.
        tau_meas: Measured joint torque per step, `(n_steps, 7)`, Nm — the observer input.
        tau_ext: The injected external torque per step, `(n_steps, 7)`, Nm — the ground truth the
            residual should recover.
        dt: The step period, s.
    """

    q: NDArray[np.float64]
    qdot: NDArray[np.float64]
    tau_meas: NDArray[np.float64]
    tau_ext: NDArray[np.float64]
    dt: float

    @property
    def n_steps(self) -> int:
        """The number of steps in the run."""
        return int(self.q.shape[0])


def default_trajectory(n_points: int, dt: float) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Build the offline excitation trajectory and its exact velocity.

    Args:
        n_points: Number of samples to generate (the caller asks for one more than the run length,
            so the momentum forward-difference has a `p_{n+1}` at every step).
        dt: The step period, s.

    Returns:
        (tuple) `(q, qdot)` each `(n_points, 7)`, with `qdot` the analytic derivative of `q`.
    """
    t = np.arange(n_points, dtype=np.float64) * dt
    amplitude = _TRAJECTORY_AMPLITUDE_RAD
    offsets = np.asarray(_TRAJECTORY_OFFSETS_RAD, dtype=np.float64)
    omegas = np.asarray(_TRAJECTORY_OMEGAS_RAD_S, dtype=np.float64)
    q = offsets[None, :] + amplitude * np.sin(np.outer(t, omegas))
    qdot = amplitude * omegas[None, :] * np.cos(np.outer(t, omegas))
    return q, qdot


def momentum_consistent_torque(
    model: GmoModelTerms,
    q: NDArray[np.float64],
    qdot: NDArray[np.float64],
    tau_ext: NDArray[np.float64],
    dt: float,
) -> NDArray[np.float64]:
    """Back-solve `tau_meas` so the momentum balance holds against `tau_ext` (the plant equation).

    Args:
        model: The model terms; the plant shares them with the observer so isolation is exact.
        q: Joint angles, `(n_points, 7)`.
        qdot: Joint velocities, `(n_points, 7)`.
        tau_ext: Injected external torque, `(n_points - 1, 7)`.
        dt: The step period, s.

    Returns:
        (NDArray[np.float64]) Measured joint torque `(n_points - 1, 7)`, Nm.
    """
    momentum = np.array([model.momentum(q[i], qdot[i]) for i in range(q.shape[0])])
    p_dot = (momentum[1:] - momentum[:-1]) / dt
    n_steps = p_dot.shape[0]
    tau_meas = np.empty((n_steps, GMO_JOINT_COUNT), dtype=np.float64)
    for i in range(n_steps):
        coriolis = model.coriolis(q[i], qdot[i])
        gravity = model.gravity(q[i])
        friction = model.friction(qdot[i])
        tau_meas[i] = p_dot[i] - coriolis + gravity + friction - tau_ext[i]
    return tau_meas


def inject_external_force(
    model: GmoModelTerms,
    joint: int,
    magnitude_nm: float,
    n_steps: int,
    dt: float = NOMINAL_DETECTION_DT_S,
    start_step: int = 0,
) -> SyntheticInjection:
    """Generate a run that injects a step external torque on one joint.

    Args:
        model: The observer's model terms (also the plant's).
        joint: Zero-based joint the external torque acts on.
        magnitude_nm: The step external torque, Nm.
        n_steps: Number of observer steps in the run.
        dt: The step period, s.
        start_step: The step the external torque switches on (zero from the start).

    Returns:
        (SyntheticInjection) The signals to drive the observer with and the ground-truth injection.

    Raises:
        GmoJointCountError: If `joint` is outside `[0, GMO_JOINT_COUNT)`.
    """
    if not 0 <= joint < GMO_JOINT_COUNT:
        raise GmoJointCountError(f"joint must be in [0, {GMO_JOINT_COUNT}), got {joint}")
    q, qdot = default_trajectory(n_steps + 1, dt)
    tau_ext = np.zeros((n_steps, GMO_JOINT_COUNT), dtype=np.float64)
    tau_ext[start_step:, joint] = magnitude_nm
    tau_meas = momentum_consistent_torque(model, q, qdot, tau_ext, dt)
    return SyntheticInjection(
        q=q[:n_steps], qdot=qdot[:n_steps], tau_meas=tau_meas, tau_ext=tau_ext, dt=dt
    )
