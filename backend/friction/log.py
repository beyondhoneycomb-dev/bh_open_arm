"""The excitation-log contract WP-2B-07 consumes from WP-2B-06 (the identification input).

An excitation log is a time series of one arm's `q`, `qd`, `qdd` and measured joint torque
`tau`, sampled at a fixed logging rate. WP-2B-06 produces it on hardware; this package defines
the shape it needs so the same schema carries synthetic logs (for the offline convergence and
separation demonstration) and real logs (for the deferred PG-FRIC-001 pass) identically.

The log is read-only data. It carries no bus handle and this package never transmits: a real
log is captured by WP-2B-05's no-transmit tap (a scheduler-internal tap or a read-only RX
socket), never by opening a second CAN writer, which would be an I-1 violation and drop the
arm (§2.1). Loading a log here touches nothing but arrays.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.friction.constants import ARM_JOINT_COUNT
from backend.friction.errors import FrictionIdentificationError


@dataclass(frozen=True)
class ExcitationLog:
    """One arm's excitation time series, sampled at a fixed logging rate.

    Attributes:
        q: Joint angles, v2 convention, radians — shape `(n_samples, ARM_JOINT_COUNT)`.
        qd: Joint velocities, rad/s — same shape.
        qdd: Joint accelerations, rad/s^2 — same shape.
        tau: Measured joint torque, Nm — same shape.
        log_freq_hz: The logging rate the samples were captured at. The identification band is
            a function of this rate (`band`), so it is part of the log, not a caller default.
    """

    q: NDArray[np.float64]
    qd: NDArray[np.float64]
    qdd: NDArray[np.float64]
    tau: NDArray[np.float64]
    log_freq_hz: float

    def __post_init__(self) -> None:
        """Refuse a log whose channels disagree in shape or whose rate is not positive.

        Raises:
            FrictionIdentificationError: On a non-2D channel, a wrong joint width, mismatched
                sample counts, or a non-positive logging rate.
        """
        channels = {"q": self.q, "qd": self.qd, "qdd": self.qdd, "tau": self.tau}
        for name, array in channels.items():
            if array.ndim != 2 or array.shape[1] != ARM_JOINT_COUNT:
                raise FrictionIdentificationError(
                    f"log channel {name!r} must have shape (n_samples, {ARM_JOINT_COUNT}), "
                    f"got {array.shape}"
                )
        sample_counts = {array.shape[0] for array in channels.values()}
        if len(sample_counts) != 1:
            raise FrictionIdentificationError(
                f"log channels disagree on sample count: "
                f"{ {name: array.shape[0] for name, array in channels.items()} }"
            )
        if not self.log_freq_hz > 0.0:
            raise FrictionIdentificationError(
                f"log_freq_hz must be strictly positive, got {self.log_freq_hz}"
            )

    @property
    def n_samples(self) -> int:
        """The number of time samples in the log."""
        return int(self.q.shape[0])

    def joint(self, index: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Return one joint's velocity and measured-torque columns.

        Args:
            index: Zero-based arm joint index (0 = joint1).

        Returns:
            (tuple) The joint's `(qd_column, tau_column)`, each length `n_samples`.
        """
        return self.qd[:, index], self.tau[:, index]
