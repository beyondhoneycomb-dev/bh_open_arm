"""The identification band is a function of the achieved logging frequency (`02b` §2.1).

The band's ceiling tracks the logging rate, the band narrows as the rate falls, the
low-speed stiction knee stops being resolved below 1 kHz, and a rate too low to place a
band at all is refused rather than returned inverted.
"""

from __future__ import annotations

import pytest

from backend.excitation import design_band
from backend.excitation.constants import STICTION_KNEE_MIN_LOGGING_HZ, STICTION_SWEEP_HZ


def test_ceiling_tracks_logging_frequency() -> None:
    # Halving the logging rate (below the mechanical cap) halves the band ceiling.
    high = design_band(1000.0)
    low = design_band(500.0)
    assert high.f_max_hz == pytest.approx(2.0 * low.f_max_hz)


def test_band_narrows_as_logging_falls() -> None:
    # A logging downgrade shrinks the identification band.
    assert design_band(625.0).span_hz < design_band(1000.0).span_hz


def test_floor_is_the_fixed_stiction_sweep() -> None:
    # The floor is the fixed zero-crossing sweep, independent of the logging rate.
    assert design_band(1000.0).f_min_hz == STICTION_SWEEP_HZ
    assert design_band(625.0).f_min_hz == STICTION_SWEEP_HZ


def test_stiction_knee_resolved_at_and_above_one_khz() -> None:
    assert design_band(STICTION_KNEE_MIN_LOGGING_HZ).resolves_stiction_knee is True
    assert design_band(1250.0).resolves_stiction_knee is True


def test_stiction_knee_unresolved_below_one_khz() -> None:
    # 02b §2.1: the tanh knee is the first casualty of a logging downgrade.
    assert design_band(999.0).resolves_stiction_knee is False
    assert design_band(625.0).resolves_stiction_knee is False


def test_non_positive_logging_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        design_band(0.0)


def test_too_low_logging_refused_as_insufficient() -> None:
    # A rate so low the ceiling cannot clear the stiction floor yields no usable band.
    with pytest.raises(ValueError, match="no usable band"):
        design_band(5.0)
