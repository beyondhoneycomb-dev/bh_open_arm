"""The release-to-CAN-stop latency artifact builder, and the forgery it refuses to publish.

This is the shared builder, not WP-1-05's measurement. WP-1-05 does not carry PG-STOP-001 as
one of its own gates, the re-verification hook rebuilds no latency from a real capture, and no
WP-1-05 acceptance asserts one. The live consumers are `backend.loadtest.stop_path`, which
records the authoritative gate as deferred and names this builder as its re-verification hook,
and `tests/wp5_05`, which drives the refusal directly. The symbols sit in this package rather
than in a consumer's tree because the alternative is two divergent copies of the one number
`04` NFR-MAN-002 forbids nailing.

`03` §5.7.0 admits a stop latency only from a single trusted clock domain: an evdev kernel
timestamp crossed with SO_TIMESTAMPING, or an independent GPIO marker. The fitted adapter
(PEAK PCAN-USB Pro FD) reports `Hardware Transmit Timestamp Modes: off` and `PTP Hardware
Clock: none`, so the instant the deadman is released cannot be timestamped in the same domain
as the CAN frame it is differenced against. A number produced anyway is two clocks subtracted,
which `03` §5.7.0 rules a forge — hence the method whitelist rather than a plausibility check
on the samples.

A real release-to-CAN-stop measurement becomes producible on this rig only with a CAN adapter
carrying hardware transmit timestamps, a PTP hardware clock disciplining both domains, or an
independent GPIO marker sampling the deadman release and the frame edge on one counter. The
builder needs no change when one of those lands: the refusal it enforces is exactly the one
the missing clock triggers, so a trusted provenance simply stops tripping it.

The builder judges no number. The `[unconfirmed]` target is recorded as a labelled reference
and never compared, so there is no pass/fail on a latency here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The re-derivation trigger is WP-1-04's, imported from that producer: this evidence is
# measured on a loop bounded by WP-1-04's provisional f_max (the `a` figure), so a confirmed
# PG-RT-001b re-derives it (`06` CI-11c). Importing rather than restating the trigger is what
# makes the WP-1-04 -> WP-1-05 consumption a real reference the graph can see.
from backend.rtbench.constants import REQUIRED_STALE_TRIGGER
from backend.torque_bringup.constants import (
    ALLOWED_CLOCK_METHODS,
    PG_STOP_001,
    STOP_LATENCY_PERCENTILE,
    STOP_LATENCY_TARGET_MS,
)


class StopLatencyArtifactRefusedError(Exception):
    """The PG-STOP-001 artifact was refused because its latency cannot be trusted.

    Raised instead of publishing when clockProvenance is absent or names a method that
    cannot correlate the release to the CAN stop frame — a stop-latency number without
    provenance is a forge, and a human trusts this before powering a brakeless arm.
    """


@dataclass(frozen=True)
class ClockProvenance:
    """How a stop-latency measurement's clock was established (`03` §5.7.0).

    Attributes:
        method: The correlation method; must be one of `ALLOWED_CLOCK_METHODS`. A candump
            hardware timestamp is not among them — it cannot correlate to the release.
        offset_sec: The measured offset between the two clocks being correlated.
        uncertainty_sec: The uncertainty of that correlation; the P99 is only meaningful
            relative to it.
    """

    method: str
    offset_sec: float
    uncertainty_sec: float

    def as_record(self) -> dict[str, Any]:
        """Render the provenance for the evidence artifact.

        Returns:
            (dict[str, Any]) The method and its offset/uncertainty.
        """
        return {
            "method": self.method,
            "offset_sec": self.offset_sec,
            "uncertainty_sec": self.uncertainty_sec,
        }


def _percentile(samples_sec: tuple[float, ...], percentile: float) -> float:
    """Return the given percentile of a sample set by nearest-rank.

    Args:
        samples_sec: The latency samples, seconds.
        percentile: The percentile to take, 0-100.

    Returns:
        (float) The nearest-rank percentile value.
    """
    ordered = sorted(samples_sec)
    rank = max(1, min(len(ordered), round(percentile / 100.0 * len(ordered))))
    return ordered[rank - 1]


def build_stop_latency_artifact(
    *,
    samples_sec: tuple[float, ...],
    clock_provenance: ClockProvenance | None,
) -> dict[str, Any]:
    """Assemble the PG-STOP-001 evidence, refusing it when the clock cannot be trusted.

    Args:
        samples_sec: Release-to-CAN-stop latency samples, seconds. Empty when the real
            measurement is deferred; then the P99 is recorded as awaited, not invented.
        clock_provenance: How the measurement clock was correlated; mandatory.

    Returns:
        (dict[str, Any]) The evidence artifact: the provenance, the P99 (or None when
        deferred), and the `[unconfirmed]` target recorded as a reference only.

    Raises:
        StopLatencyArtifactRefusedError: If clockProvenance is absent (⑥) or names a method
            that cannot correlate the release to the CAN stop frame (the candump forge).
    """
    if clock_provenance is None:
        raise StopLatencyArtifactRefusedError(
            "no clockProvenance; a release-to-CAN-stop latency without provenance is "
            "unfalsifiable and is refused (03 §5.7.0, acceptance ⑥)"
        )
    if clock_provenance.method not in ALLOWED_CLOCK_METHODS:
        raise StopLatencyArtifactRefusedError(
            f"clockProvenance method {clock_provenance.method!r} cannot correlate the release "
            "to the CAN stop frame; a candump HW timestamp is a forge, not a measurement "
            "(03 §5.7.0)"
        )

    # The P99 is published only when there are real samples to compute it from. Comparability
    # is proven by the provenance above; without samples the tail is awaited, not zero.
    p99_sec = _percentile(samples_sec, STOP_LATENCY_PERCENTILE) if samples_sec else None

    return {
        "gate": PG_STOP_001,
        "clock_provenance": clock_provenance.as_record(),
        "sample_count": len(samples_sec),
        "percentile": STOP_LATENCY_PERCENTILE,
        "p99_sec": p99_sec,
        # Recorded as a reference, never a gate: 20 ms is an [unconfirmed] target and the
        # measured P99 is canon (04 NFR-MAN-002, acceptance ⑬). No comparison is made here.
        "reference_target_ms_unconfirmed": STOP_LATENCY_TARGET_MS,
        "reference_note": (
            "04 NFR-MAN-002's 20 ms is an [unconfirmed] target recorded for reference only; "
            "the measured P99 is canonical and the rig confirms it — this evidence renders no "
            "pass/fail on the latency (acceptance ⑬)"
        ),
        "stale_on": [REQUIRED_STALE_TRIGGER],
    }
