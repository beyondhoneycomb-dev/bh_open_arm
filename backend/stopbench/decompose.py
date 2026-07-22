"""Path decomposition of the lease-expiry -> CAN-hold-frame-first-byte latency.

This is the genuinely new machinery of WP-2A-06. WP-1-05 already measures the total
release-to-CAN-stop P99 with its mandatory `clockProvenance` (`backend.torque_bringup.
stop_latency`), and this bench reuses that for the total; what it adds is the *split* of
that one interval into the four stages `02b` WP-2A-06 names — harness-event, transmit,
scheduler, CAN — so a stop-latency regression can be attributed to a stage rather than
seen only as a moved aggregate.

A sample is five boundary timestamps on **one** clock domain. That single-domain premise
is not this module's to prove: it is exactly what `03` §5.7.0's `clockProvenance` attests,
and the bench refuses to publish without it (`backend.stopbench.bench`). Given comparable
timestamps, the four segment durations are consecutive differences and telescope back to
the total, which is the property a decomposition must hold and `test_decompose` checks.

Full distributions, never summary-only: each segment and the total are held as a
`CycleTimeHistogram` (`sim.harness.histogram`, WP-0C-06), which keeps every raw sample and
renders the whole binned histogram. That is the same discipline `03` §5.7 demands of this
gate ("요약통계만 금지, 히스토그램 첨부"), so the histogram collector is reused rather than a
percentile triple recomputed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from sim.harness.histogram import CycleTimeHistogram


class StopPathSegment(Enum):
    """The four stages the stop path is decomposed into (`02b` WP-2A-06).

    Ordered as they occur in time: the deadman release surfaces as a harness event,
    is transmitted to the scheduler host, is turned into a hold frame by one scheduler
    tick, and is written to the CAN bus. A stop-latency regression lands in exactly one
    of these, which is why the split is worth carrying.
    """

    HARNESS_EVENT = "harness_event"
    TRANSMIT = "transmit"
    SCHEDULER = "scheduler"
    CAN = "can"


# The segment order, fixed so the record and the histograms iterate identically.
SEGMENT_ORDER: tuple[StopPathSegment, ...] = (
    StopPathSegment.HARNESS_EVENT,
    StopPathSegment.TRANSMIT,
    StopPathSegment.SCHEDULER,
    StopPathSegment.CAN,
)


class NonMonotonicSampleError(ValueError):
    """A sample's five boundary timestamps do not increase monotonically.

    A decomposition built from out-of-order timestamps is meaningless — a segment would
    carry a negative duration — so the sample is refused at construction rather than
    silently producing a nonsense split.
    """


@dataclass(frozen=True)
class StopPathSample:
    """One deadman-release-to-CAN-first-byte event, as five boundary timestamps.

    All five are seconds on a single monotonic clock domain; their comparability is what
    `03` §5.7.0's `clockProvenance` attests, and the bench refuses to publish a
    decomposition whose provenance is absent or names the candump forge. The four segment
    durations are the consecutive differences and telescope to `total`.

    Attributes:
        lease_expiry_at: The deadman lease expiry the harness recorded (path start).
        transmit_at: The expiry handed to the transmit path (harness-event -> transmit).
        scheduler_at: The scheduler tick that read the expiry (transmit -> scheduler).
        can_write_at: The `mit_control_batch` call that wrote the hold (scheduler -> CAN).
        can_first_byte_at: The first byte of the hold frame on the bus (path end).
    """

    lease_expiry_at: float
    transmit_at: float
    scheduler_at: float
    can_write_at: float
    can_first_byte_at: float

    def __post_init__(self) -> None:
        """Refuse a sample whose boundaries are not monotonically non-decreasing.

        Raises:
            NonMonotonicSampleError: If any boundary precedes the one before it.
        """
        boundaries = (
            self.lease_expiry_at,
            self.transmit_at,
            self.scheduler_at,
            self.can_write_at,
            self.can_first_byte_at,
        )
        for earlier, later in zip(boundaries, boundaries[1:], strict=False):
            if later < earlier:
                raise NonMonotonicSampleError(
                    f"stop-path boundaries must be monotonic; got {boundaries}"
                )

    def segment_durations(self) -> dict[StopPathSegment, float]:
        """Return the four segment durations, in seconds.

        Returns:
            (dict[StopPathSegment, float]) Each stage's duration; the four sum to `total`.
        """
        return {
            StopPathSegment.HARNESS_EVENT: self.transmit_at - self.lease_expiry_at,
            StopPathSegment.TRANSMIT: self.scheduler_at - self.transmit_at,
            StopPathSegment.SCHEDULER: self.can_write_at - self.scheduler_at,
            StopPathSegment.CAN: self.can_first_byte_at - self.can_write_at,
        }

    def total(self) -> float:
        """Return the whole lease-expiry-to-CAN-first-byte latency, in seconds.

        Returns:
            (float) `can_first_byte_at - lease_expiry_at`.
        """
        return self.can_first_byte_at - self.lease_expiry_at

    def reconciles(self, tolerance_sec: float = 1e-9) -> bool:
        """Whether the four segments sum back to the total within a tolerance.

        The equality is exact in real arithmetic (the segments telescope); the tolerance
        only absorbs floating-point re-association. A sample that fails this is not a
        rounding artifact but a boundary defined wrong.

        Args:
            tolerance_sec: Allowed absolute difference, seconds.

        Returns:
            (bool) True when `sum(segments)` equals `total` within `tolerance_sec`.
        """
        return abs(sum(self.segment_durations().values()) - self.total()) <= tolerance_sec


class StopPathDecomposition:
    """Per-segment and total latency distributions over a set of stop-path samples.

    Ownership: holds its own `CycleTimeHistogram` per segment and one for the total, each
    built from an immutable sample copy. The histograms are the full distributions
    (`03` §5.7 forbids summary-only), and this object never decides a pass line — the
    numeric target stays `[unconfirmed]` (WP-2A-06 acceptance ②).
    """

    def __init__(self, samples: Sequence[StopPathSample]) -> None:
        """Aggregate samples into per-segment and total histograms.

        Args:
            samples: The stop-path samples to decompose; may be empty when the real
                measurement is deferred, in which case every distribution is empty rather
                than fabricated.
        """
        self._sample_count = len(samples)
        per_segment: dict[StopPathSegment, list[float]] = {segment: [] for segment in SEGMENT_ORDER}
        totals: list[float] = []
        for sample in samples:
            durations = sample.segment_durations()
            for segment in SEGMENT_ORDER:
                per_segment[segment].append(durations[segment])
            totals.append(sample.total())
        self._segments = {
            segment: CycleTimeHistogram(np.array(values, dtype=np.float64))
            for segment, values in per_segment.items()
        }
        self._total = CycleTimeHistogram(np.array(totals, dtype=np.float64))

    @property
    def sample_count(self) -> int:
        """Number of samples the decomposition was built from."""
        return self._sample_count

    def segment(self, segment: StopPathSegment) -> CycleTimeHistogram:
        """Return the full distribution of one segment's durations.

        Args:
            segment: The stage to read.

        Returns:
            (CycleTimeHistogram) The segment's distribution.
        """
        return self._segments[segment]

    def total(self) -> CycleTimeHistogram:
        """Return the full distribution of the total stop-path latency.

        Returns:
            (CycleTimeHistogram) The total-latency distribution.
        """
        return self._total

    def as_record(self) -> dict[str, Any]:
        """Serialize the decomposition for the evidence artifact.

        Returns:
            (dict[str, Any]) `sample_count`, one full histogram per segment keyed by its
            name, and the total-latency histogram — the path decomposition WP-2A-06
            acceptance ① requires be recorded.
        """
        return {
            "sample_count": self._sample_count,
            "segments": {
                segment.value: self._segments[segment].as_record() for segment in SEGMENT_ORDER
            },
            "total": self._total.as_record(),
        }
