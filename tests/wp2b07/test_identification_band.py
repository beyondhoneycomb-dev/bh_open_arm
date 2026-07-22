"""Acceptance ③: the identification band is recorded as a function of the logging frequency.

§2.1 makes the band rate-dependent: the stiction knee is the first thing lost when the logging
rate drops. This checks that the recorded band's lower edge rises as the rate falls, and that a
low enough rate reports the knee as unresolved.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.friction import IdentificationResult, SyntheticLog, band_from_identification
from backend.friction.band import identification_band
from backend.friction.constants import LOG_FREQ_REFERENCE_HZ
from backend.friction.errors import FrictionIdentificationError

_KNEE_OMEGA = 0.18
_OMEGA_HI = 2.0


def test_band_is_recorded_in_the_metadata(document: dict[str, Any]) -> None:
    band = document["identification_band"]
    assert band["log_freq_hz"] == LOG_FREQ_REFERENCE_HZ
    assert band["omega_hi_rad_s"] > band["omega_lo_rad_s"]
    assert "logging frequency" in band["note"]


def test_lower_rate_raises_the_stiction_edge() -> None:
    fast = identification_band(1000.0, _OMEGA_HI, _KNEE_OMEGA)
    slow = identification_band(100.0, _OMEGA_HI, _KNEE_OMEGA)
    # omega_lo scales inversely with the rate: a tenth of the rate is ten times the edge.
    assert slow.omega_lo_rad_s == pytest.approx(10.0 * fast.omega_lo_rad_s)


def test_a_low_rate_loses_the_knee() -> None:
    fast = identification_band(1000.0, _OMEGA_HI, _KNEE_OMEGA)
    slow = identification_band(40.0, _OMEGA_HI, _KNEE_OMEGA)
    assert fast.knee_resolved
    assert not slow.knee_resolved


def test_band_from_identification_uses_the_log_rate(
    synthetic: SyntheticLog, result: IdentificationResult
) -> None:
    band = band_from_identification(synthetic.log, result)
    assert band.log_freq_hz == synthetic.log.log_freq_hz
    assert band.knee_resolved


def test_non_positive_rate_is_refused() -> None:
    with pytest.raises(FrictionIdentificationError):
        identification_band(0.0, _OMEGA_HI, _KNEE_OMEGA)
