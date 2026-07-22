"""The trusted-clock refusal for the reaction-time measurement.

The reaction time spans a software event — detection confirmed inside the control loop — and
a bus event — the first byte of the reaction MIT frame on CAN. Correlating the two needs the
same instrumentation the stop path needs (`03` §5.7.0: an evdev kernel timestamp crossed
with SO_TIMESTAMPING, or an independent GPIO marker). A candump hardware timestamp cannot be
correlated to the confirm event, so a reaction time built from one is a forge, not a
measurement. This module refuses to accept an absent or forged clock, which is the offline-
testable core of THE ONE RULE: a forged clock can never manufacture a reaction-time number.

The set of trusted methods is not redefined here. `ALLOWED_CLOCK_METHODS` has one home,
`backend.torque_bringup.constants` (WP-1-05, `03` §5.7.0 forgery ruling), and is imported —
consuming that single source, not forking a second trust decision the audit would hunt for.
The `ClockProvenance` record type is reused from the same producer for the same reason.
"""

from __future__ import annotations

from backend.torque_bringup import ClockProvenance
from backend.torque_bringup.constants import ALLOWED_CLOCK_METHODS


class ReactionLatencyRefusedError(Exception):
    """The reaction-time evidence was refused because its clock cannot be trusted.

    Raised instead of publishing when clockProvenance is absent or names a method that
    cannot correlate the confirm event to the CAN frame's first byte — a reaction time
    without trustworthy provenance is a forge, and this bench never fakes a measured
    reaction time (THE ONE RULE).
    """


def assert_trusted_clock(clock_provenance: ClockProvenance | None) -> ClockProvenance:
    """Refuse to proceed unless the clock provenance is present and trusted.

    Args:
        clock_provenance: How the measurement clock was correlated; mandatory, and judged
            against the single-source `ALLOWED_CLOCK_METHODS` set.

    Returns:
        (ClockProvenance) The trusted provenance, for the caller to record as evidence.

    Raises:
        ReactionLatencyRefusedError: If the provenance is absent, or names a method that
            cannot correlate the confirm event to the CAN frame's first byte (the candump
            forge).
    """
    if clock_provenance is None:
        raise ReactionLatencyRefusedError(
            "no clockProvenance; a detection-confirm-to-CAN-first-byte reaction time without "
            "provenance is unfalsifiable and is refused (03 §5.7.0)"
        )
    if clock_provenance.method not in ALLOWED_CLOCK_METHODS:
        raise ReactionLatencyRefusedError(
            f"clockProvenance method {clock_provenance.method!r} cannot correlate the confirm "
            "event to the reaction frame's first byte; a candump HW timestamp is a forge, not "
            "a measurement (03 §5.7.0)"
        )
    return clock_provenance
