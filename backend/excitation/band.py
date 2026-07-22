"""The identification band as a function of the achieved logging frequency (`WP-2B-06`).

`02b` §2.1 fixes the relationship this module encodes: the exciting trajectory's
frequency content is bounded above by the achieved logging (= tick) rate, not chosen
freely. The band's ceiling is `f_log / MIN_SAMPLES_PER_CYCLE` capped at the joint's
mechanical bandwidth; its floor is a fixed slow sweep that carries velocity through
the stiction region. When `f_log` falls the ceiling falls with it and the band
narrows, and below 1 kHz the low-speed `tanh` knee is under-sampled — the first
casualty of a logging downgrade (`02b` §2.1). A band that cannot resolve that knee is
reported as such so `PG-FRIC-001` can degrade honestly rather than claim a stiction
fit it did not earn.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.excitation.constants import (
    IDENT_FREQ_CAP_HZ,
    MIN_SAMPLES_PER_CYCLE,
    STICTION_KNEE_MIN_LOGGING_HZ,
    STICTION_SWEEP_HZ,
)


@dataclass(frozen=True)
class ExcitationBand:
    """The frequency band an exciting trajectory occupies, derived from a logging rate.

    Attributes:
        logging_frequency_hz: The achieved logging/tick rate the band was derived from.
        f_min_hz: The band's fixed lower edge — the stiction zero-crossing sweep.
        f_max_hz: The band's upper edge, a function of `logging_frequency_hz`.
        resolves_stiction_knee: Whether the logging rate is high enough for the
            low-speed `tanh` knee to be resolved. False means the viscous and Coulomb
            terms are still identifiable but the stiction fit is provisional at best.
    """

    logging_frequency_hz: float
    f_min_hz: float
    f_max_hz: float
    resolves_stiction_knee: bool

    @property
    def span_hz(self) -> float:
        """The width of the band, `f_max_hz - f_min_hz`."""
        return self.f_max_hz - self.f_min_hz


def design_band(logging_frequency_hz: float) -> ExcitationBand:
    """Derive the identification band from an achieved logging frequency.

    The ceiling is the smaller of the sampling-derived limit (`f_log /
    MIN_SAMPLES_PER_CYCLE`) and the joint mechanical-bandwidth cap; the floor is the
    fixed stiction sweep. A logging rate too low to place the ceiling above the floor
    yields no usable band and is refused rather than returned inverted.

    Args:
        logging_frequency_hz: The achieved logging (= scheduler tick) rate, Hz. Must be
            positive; a run reports it from `WP-2B-05`.

    Returns:
        (ExcitationBand) The band to fill, with its stiction-knee resolution flag set
        from whether `logging_frequency_hz` clears `STICTION_KNEE_MIN_LOGGING_HZ`.

    Raises:
        ValueError: If `logging_frequency_hz` is not positive, or is so low that the
            band ceiling would not clear the fixed stiction floor.
    """
    if logging_frequency_hz <= 0.0:
        raise ValueError(f"logging frequency must be positive, got {logging_frequency_hz}")

    f_max = min(logging_frequency_hz / MIN_SAMPLES_PER_CYCLE, IDENT_FREQ_CAP_HZ)
    if f_max <= STICTION_SWEEP_HZ:
        raise ValueError(
            f"logging frequency {logging_frequency_hz} Hz yields a band ceiling {f_max} Hz "
            f"at or below the stiction floor {STICTION_SWEEP_HZ} Hz: no usable band, so "
            f"excitation is insufficient at this rate (02b §2.1 branch)"
        )
    return ExcitationBand(
        logging_frequency_hz=logging_frequency_hz,
        f_min_hz=STICTION_SWEEP_HZ,
        f_max_hz=f_max,
        resolves_stiction_knee=logging_frequency_hz >= STICTION_KNEE_MIN_LOGGING_HZ,
    )
