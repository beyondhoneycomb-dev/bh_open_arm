"""A synthetic excitation log with known friction and injected gravity/inertia (offline demo).

THE ONE RULE forbids presenting a synthetic-log fit as a real PG-FRIC-001 pass, and this module
is the synthetic log. It exists to prove the identification *math* — that the per-joint fit
converges and that the residual separates from the gravity and inertia terms — on a signal
whose friction is known exactly, so recovery can be checked against ground truth.

The measured torque is built as `M*qdd + C*qd + g` (the real committed-v2 inverse dynamics, so
the gravity and inertia are genuine, not a toy) plus the four-term tanh friction at known
parameters plus Gaussian measurement noise. Because the basis subtracted during identification
is the same rigid-body inverse dynamics — and never the friction result — recovering the
injected parameters demonstrates the separation without any self-approval. The trajectory is a
per-joint multi-sine whose velocity crosses zero, so the stiction knee is actually excited.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from backend.friction.basis import InverseDynamicsBasis
from backend.friction.constants import (
    ARM_JOINT_COUNT,
    LOG_FREQ_REFERENCE_HZ,
    SYNTHETIC_LOG_SEED,
)
from backend.friction.log import ExcitationLog
from backend.friction.model import FrictionParams
from backend.friction.seed import V1_SEED_FRICTION

# The excitation frequencies (Hz) of the multi-sine and each joint's share of its velocity
# amplitude across them. The tones are high enough that several full cycles fit the window, so
# the velocity oscillates symmetrically through zero many times — a slow ramp that stayed
# one-signed would never excite the tanh knee and would leave Fo and Fc unidentifiable.
_EXCITATION_FREQS_HZ = np.array([0.8, 1.7, 2.9])
_AMPLITUDE_SHARE = np.array([0.5, 0.3, 0.2])

# Per-joint peak velocity amplitude (rad/s) and the mid-range pose the excitation oscillates
# about, kept inside the v2 joint limits so the synthetic poses are physical. The position swing
# is amplitude/omega, so with these frequencies the pose stays within a few tenths of a radian.
_JOINT_PEAK_RAD_S = np.array([2.5, 2.0, 2.2, 1.8, 1.5, 1.4, 1.2])
_CENTER_POSE_RAD = np.array([0.2, 1.0, 0.0, 0.9, 0.0, 0.0, 0.0])

_DEFAULT_DURATION_S = 2.5
_DEFAULT_NOISE_NM = 0.02

# The synthetic v2 "truth" differs from the v1 seed by a per-term scale, so the fit recovers a
# v2 value distinct from the seed and the relative-error table (acceptance ④) is non-trivial.
_V2_SCALE_FO = 1.10
_V2_SCALE_FV = 0.85
_V2_SCALE_FC = 1.25
_V2_SCALE_K = 1.10


def default_truth() -> tuple[FrictionParams, ...]:
    """Return the synthetic v2 ground-truth friction: the v1 seed scaled per term.

    Returns:
        (tuple[FrictionParams, ...]) The injected parameters, joint1..joint7 order.
    """
    return tuple(
        FrictionParams.from_stored_k(
            f_o=seed.f_o * _V2_SCALE_FO,
            f_v=seed.f_v * _V2_SCALE_FV,
            f_c=seed.f_c * _V2_SCALE_FC,
            k=seed.k * _V2_SCALE_K,
        )
        for seed in V1_SEED_FRICTION
    )


@dataclass(frozen=True)
class SyntheticLog:
    """A synthetic excitation log paired with the friction it was built from.

    Attributes:
        log: The excitation log (with genuine v2 gravity/inertia and known friction).
        truth: The per-joint friction parameters injected, joint1..joint7 order.
    """

    log: ExcitationLog
    truth: tuple[FrictionParams, ...]


def _kinematics(n_samples: int, log_freq_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build consistent `q`, `qd`, `qdd` multi-sine trajectories for the whole arm.

    Args:
        n_samples: Number of time samples.
        log_freq_hz: The sampling rate, Hz.

    Returns:
        (tuple) `(q, qd, qdd)`, each `(n_samples, ARM_JOINT_COUNT)`.
    """
    time = np.arange(n_samples, dtype=np.float64) / log_freq_hz
    omega = 2.0 * np.pi * _EXCITATION_FREQS_HZ
    q = np.zeros((n_samples, ARM_JOINT_COUNT), dtype=np.float64)
    qd = np.zeros((n_samples, ARM_JOINT_COUNT), dtype=np.float64)
    qdd = np.zeros((n_samples, ARM_JOINT_COUNT), dtype=np.float64)
    for joint in range(ARM_JOINT_COUNT):
        amplitudes = _JOINT_PEAK_RAD_S[joint] * _AMPLITUDE_SHARE
        for tone, (amp, w) in enumerate(zip(amplitudes, omega, strict=True)):
            phase = 0.6 * joint + 1.7 * tone
            angle = w * time + phase
            qd[:, joint] += amp * np.sin(angle)
            qdd[:, joint] += amp * w * np.cos(angle)
            q[:, joint] += -(amp / w) * np.cos(angle)
        q[:, joint] += _CENTER_POSE_RAD[joint]
    return q, qd, qdd


def _friction_torque(qd: np.ndarray, truth: Sequence[FrictionParams]) -> np.ndarray:
    """Evaluate the injected friction at every sample and joint.

    Args:
        qd: Joint velocities, `(n_samples, ARM_JOINT_COUNT)`.
        truth: The per-joint injected friction parameters.

    Returns:
        (np.ndarray) Friction torque, `(n_samples, ARM_JOINT_COUNT)`.
    """
    friction = np.zeros_like(qd)
    for joint in range(ARM_JOINT_COUNT):
        friction[:, joint] = truth[joint].tau(qd[:, joint])
    return friction


def generate_synthetic_log(
    basis: InverseDynamicsBasis,
    log_freq_hz: float = LOG_FREQ_REFERENCE_HZ,
    duration_s: float = _DEFAULT_DURATION_S,
    noise_nm: float = _DEFAULT_NOISE_NM,
    seed: int = SYNTHETIC_LOG_SEED,
    truth: Sequence[FrictionParams] | None = None,
) -> SyntheticLog:
    """Generate a synthetic excitation log with genuine v2 dynamics and known friction.

    Args:
        basis: The inverse-dynamics basis whose model torque is the injected dynamics.
        log_freq_hz: The logging rate to synthesise at, Hz.
        duration_s: The log duration, seconds.
        noise_nm: Standard deviation of the additive Gaussian torque noise, Nm.
        seed: Deterministic RNG seed for the noise.
        truth: The per-joint friction to inject; the default synthetic v2 truth when None.

    Returns:
        (SyntheticLog) The log and the injected friction parameters.
    """
    injected = tuple(truth) if truth is not None else default_truth()
    n_samples = max(1, int(duration_s * log_freq_hz))
    q, qd, qdd = _kinematics(n_samples, log_freq_hz)
    placeholder = ExcitationLog(q=q, qd=qd, qdd=qdd, tau=np.zeros_like(q), log_freq_hz=log_freq_hz)
    model_torque = basis.evaluate(placeholder).total
    friction = _friction_torque(qd, injected)
    noise = np.random.default_rng(seed).normal(0.0, noise_nm, size=q.shape)
    tau = model_torque + friction + noise
    log = ExcitationLog(q=q, qd=qd, qdd=qdd, tau=tau, log_freq_hz=log_freq_hz)
    return SyntheticLog(log=log, truth=injected)
