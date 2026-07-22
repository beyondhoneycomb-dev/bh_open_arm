"""The per-joint residual max/sigma collector for the calibration wizard (WP-2C-03).

`12` FR-SAF-060 asks the wizard to run a representative collision-free trajectory
*repeatedly* and collect, per joint, the residual's maximum absolute value and its standard
deviation. This collector is the accumulator: each run's residual samples are folded in
without retaining them, so an arbitrarily long calibration session costs constant memory.

The variance is combined across runs with Chan's parallel algorithm rather than a running
sum of squares, because the residual mean is small relative to individual samples and a
naive sum-of-squares loses precision exactly where the standard deviation is smallest — the
low-residual joints whose thresholds sit closest to the noise floor. The standard deviation
is the sample statistic (ddof=1): the runs are a sample of the trajectory's behaviour, not
the whole population, and a proposal is refused below two samples where it is undefined.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.safety_bringup.constants import ARM_JOINT_COUNT
from backend.threshold_calib.constants import (
    MIN_RUNS_FOR_PROPOSAL,
    MIN_SAMPLES_FOR_PROPOSAL,
)


class CollectorError(Exception):
    """Raised when a run's shape is wrong or stats are requested before enough data."""


@dataclass(frozen=True)
class ResidualStats:
    """The collision-free residual statistics of one joint (`12` FR-SAF-060).

    Attributes:
        joint_index: Zero-based arm joint index (0 == J1).
        max_abs_nm: Largest residual magnitude seen over every run, Nm.
        sigma_nm: Sample standard deviation of the residual over every run, Nm.
        mean_nm: Mean residual over every run, Nm.
        sample_count: Total residual samples folded in across all runs.
    """

    joint_index: int
    max_abs_nm: float
    sigma_nm: float
    mean_nm: float
    sample_count: int


class ResidualCollector:
    """Accumulate per-joint residual max/sigma across repeated collision-free runs.

    The collector holds only running aggregates, never the samples, so a long calibration
    session does not grow without bound. It is single-threaded state owned by the wizard
    driving the runs; it assumes no concurrent `add_run`.
    """

    def __init__(self, joint_count: int) -> None:
        """Create an empty collector for a fixed joint count.

        Args:
            joint_count: Number of joints each run reports a residual column for.
        """
        self.mJointCount = joint_count
        self.mRunCount = 0
        self.mCount = np.zeros(joint_count, dtype=np.int64)
        self.mMean = np.zeros(joint_count, dtype=np.float64)
        self.mM2 = np.zeros(joint_count, dtype=np.float64)
        self.mMaxAbs = np.zeros(joint_count, dtype=np.float64)

    def add_run(self, residuals: NDArray[np.float64]) -> None:
        """Fold one run's residual samples into the running aggregates.

        Args:
            residuals: A `(n_samples, joint_count)` array of per-joint residual torque, Nm.

        Raises:
            CollectorError: If the array is not two-dimensional, has the wrong joint width,
                or carries no samples.
        """
        run = np.asarray(residuals, dtype=np.float64)
        if run.ndim != 2 or run.shape[1] != self.mJointCount:
            raise CollectorError(
                f"run must be (n_samples, {self.mJointCount}); got shape {run.shape}"
            )
        if run.shape[0] == 0:
            raise CollectorError("run carries no samples")

        batch_count = run.shape[0]
        batch_mean = run.mean(axis=0)
        # M2 is the sum of squared deviations, the numerator of the sample variance; Chan's
        # combine keeps it stable when a later run's mean differs from the accumulated one.
        batch_m2 = ((run - batch_mean) ** 2).sum(axis=0)

        combined = self.mCount + batch_count
        delta = batch_mean - self.mMean
        self.mMean = self.mMean + delta * (batch_count / combined)
        self.mM2 = self.mM2 + batch_m2 + delta**2 * (self.mCount * batch_count / combined)
        self.mCount = combined
        self.mMaxAbs = np.maximum(self.mMaxAbs, np.abs(run).max(axis=0))
        self.mRunCount += 1

    def run_count(self) -> int:
        """Return how many runs have been folded in.

        Returns:
            (int) The number of `add_run` calls accepted.
        """
        return self.mRunCount

    def stats(self) -> tuple[ResidualStats, ...]:
        """Return the per-joint residual statistics, one entry per joint.

        Returns:
            (tuple[ResidualStats, ...]) Per-joint max magnitude, sample sigma and mean.

        Raises:
            CollectorError: If fewer than the minimum runs or per-joint samples have been
                collected, where a maximum is not an envelope and a sigma is undefined.
        """
        if self.mRunCount < MIN_RUNS_FOR_PROPOSAL:
            raise CollectorError(
                f"need at least {MIN_RUNS_FOR_PROPOSAL} runs to propose; have {self.mRunCount}"
            )
        if int(self.mCount.min()) < MIN_SAMPLES_FOR_PROPOSAL:
            raise CollectorError(
                f"every joint needs at least {MIN_SAMPLES_FOR_PROPOSAL} samples; "
                f"the sparsest has {int(self.mCount.min())}"
            )
        variance = self.mM2 / (self.mCount - 1)
        sigma = np.sqrt(variance)
        return tuple(
            ResidualStats(
                joint_index=index,
                max_abs_nm=float(self.mMaxAbs[index]),
                sigma_nm=float(sigma[index]),
                mean_nm=float(self.mMean[index]),
                sample_count=int(self.mCount[index]),
            )
            for index in range(self.mJointCount)
        )


def collector_for_arm() -> ResidualCollector:
    """Return a residual collector sized for the seven actuated arm joints.

    Returns:
        (ResidualCollector) An empty collector over `ARM_JOINT_COUNT` joints.
    """
    return ResidualCollector(ARM_JOINT_COUNT)
