"""The identification band as a function of the logging frequency (acceptance ③, §2.1).

Friction is only identified over the velocity range the log actually resolves. The upper edge
is the fastest velocity the excitation reached. The lower edge is set by the logging rate: the
stiction knee sits near `omega = 1/k_eff`, and resolving it needs low-velocity samples whose
density scales with the rate. §2.1 states the consequence — when the achieved tick rate falls
below 1 kHz, "the tanh knee, the low-speed stiction region, is the first thing lost". This
module makes that quantitative: `omega_lo` rises as the rate falls, and `knee_resolved` records
whether the tightest knee still lands inside the band.

The band is recorded in the friction.yaml metadata so a consumer knows the velocity range the
parameters are trustworthy over, and knows a low-rate identification did not cover the knee.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.friction.constants import (
    KNEE_RESOLUTION_AT_REFERENCE_RAD_S,
    LOG_FREQ_REFERENCE_HZ,
)
from backend.friction.errors import FrictionIdentificationError
from backend.friction.identify import IdentificationResult
from backend.friction.log import ExcitationLog


@dataclass(frozen=True)
class IdentificationBand:
    """The velocity range a friction identification is trustworthy over.

    Attributes:
        log_freq_hz: The logging rate the band is derived from.
        omega_lo_rad_s: The lower (stiction) edge, rad/s — a function of the logging rate.
        omega_hi_rad_s: The upper edge, rad/s — the fastest velocity the excitation reached.
        knee_omega_rad_s: The tightest tanh knee across joints, `min(1/k_eff)`, rad/s.
        knee_resolved: Whether the tightest knee lands at or above `omega_lo_rad_s`, i.e. inside
            the resolved band. False means the low-rate log lost the stiction knee (§2.1).
    """

    log_freq_hz: float
    omega_lo_rad_s: float
    omega_hi_rad_s: float
    knee_omega_rad_s: float
    knee_resolved: bool


def identification_band(
    log_freq_hz: float, omega_hi_rad_s: float, knee_omega_rad_s: float
) -> IdentificationBand:
    """Build the identification band from the logging rate and the excitation.

    Args:
        log_freq_hz: The achieved logging rate, Hz.
        omega_hi_rad_s: The fastest velocity the excitation reached, rad/s.
        knee_omega_rad_s: The tightest tanh knee across joints, rad/s.

    Returns:
        (IdentificationBand) The band, with its rate-dependent lower edge.

    Raises:
        FrictionIdentificationError: On a non-positive logging rate.
    """
    if not log_freq_hz > 0.0:
        raise FrictionIdentificationError(f"log_freq_hz must be positive, got {log_freq_hz}")
    omega_lo = KNEE_RESOLUTION_AT_REFERENCE_RAD_S * (LOG_FREQ_REFERENCE_HZ / log_freq_hz)
    return IdentificationBand(
        log_freq_hz=float(log_freq_hz),
        omega_lo_rad_s=float(omega_lo),
        omega_hi_rad_s=float(abs(omega_hi_rad_s)),
        knee_omega_rad_s=float(knee_omega_rad_s),
        knee_resolved=bool(knee_omega_rad_s >= omega_lo),
    )


def band_from_identification(
    log: ExcitationLog, result: IdentificationResult
) -> IdentificationBand:
    """Derive the band from a completed identification: rate from the log, edges from the fit.

    Args:
        log: The excitation log identified against.
        result: The identification result whose `k_eff` values set the knee.

    Returns:
        (IdentificationBand) The band for this identification.
    """
    omega_hi = float(np.max(np.abs(log.qd)))
    knee_omega = min(1.0 / fit.params.k_eff for fit in result.fits)
    return identification_band(log.log_freq_hz, omega_hi, knee_omega)
