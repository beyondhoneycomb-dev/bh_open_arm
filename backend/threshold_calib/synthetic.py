"""A synthetic collision-free residual stream (offline demonstration).

THE ONE RULE forbids presenting a synthetic-stream calibration as a real measured
threshold, and this module is the synthetic stream. It exists to prove the calibration
*math* — that the collector's streaming per-joint max and sigma equal a batch computation
over the same samples, and that the proposal rules land where the statistics say — on a
signal that runs entirely offline, with no hardware.

The residual is a reproducible zero-mean Gaussian per joint at a chosen sigma, one draw per
run seeded from the run index, so a session of several runs is deterministic yet the runs
differ. The generating sigma is the residual scale of a collision-free trajectory: small,
and smallest at the low-torque wrist, where a `max + 3sigma` proposal naturally lands near
the ten-LSB floor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.safety_bringup.constants import ARM_JOINT_COUNT

# The default synthetic per-joint residual sigma, Nm: small relative to the arm's torque
# scale and smallest at the wrist, so a collision-free run's residual envelope resembles the
# real one the wizard would collect.
_DEFAULT_SIGMA_NM: NDArray[np.float64] = np.array(
    [0.05, 0.05, 0.03, 0.03, 0.006, 0.006, 0.006], dtype=np.float64
)
_SYNTHETIC_SEED = 20260722
_SAMPLES_PER_RUN = 500


@dataclass(frozen=True)
class SyntheticTruth:
    """The generating envelope a synthetic stream was drawn from.

    Attributes:
        sigma_nm: Per-joint generating standard deviation, Nm; the collected sample sigma
            converges to this as the run count grows.
    """

    sigma_nm: tuple[float, ...]


def synthetic_truth() -> SyntheticTruth:
    """Return the generating envelope of the default synthetic stream.

    Returns:
        (SyntheticTruth) The per-joint generating sigma.
    """
    return SyntheticTruth(sigma_nm=tuple(float(v) for v in _DEFAULT_SIGMA_NM))


def synthetic_residual_run(run_index: int, samples: int = _SAMPLES_PER_RUN) -> NDArray[np.float64]:
    """Generate one collision-free synthetic residual run at the default envelope.

    Args:
        run_index: Index of the run within a session; it seeds the generator so repeated
            runs differ while the whole session stays reproducible.
        samples: Number of residual samples in the run.

    Returns:
        (NDArray[np.float64]) A `(samples, ARM_JOINT_COUNT)` zero-mean Gaussian residual
        array, Nm, at the default per-joint sigma.
    """
    rng = np.random.default_rng(_SYNTHETIC_SEED + run_index)
    run: NDArray[np.float64] = rng.normal(0.0, 1.0, size=(samples, ARM_JOINT_COUNT))
    return run * _DEFAULT_SIGMA_NM
