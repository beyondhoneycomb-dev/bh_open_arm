"""Decomposition of the detection-confirm -> first-reaction-MIT-frame latency.

This is the genuinely new machinery of WP-2C-06. The reaction *time* the plan defines is
one interval — detection confirmed (`WP-2C-04`) to the first reaction MIT frame on the bus
(`WP-2C-05`) — and this module splits that one interval into the three consecutive stages
the reaction path actually has, so a reaction-time regression can be attributed to a stage
rather than seen only as a moved aggregate. The stages are also exactly the levers the
negative branch names: an over-target reaction retunes the observer / shortens the reaction
path (`02b` WP-2C-06 negative branch), which is a choice you can only make if you know which
stage the time is in.

The reaction path is *same-process* — detection and reaction share one control process and
the feedback is a single function call (`02b` WP-2C-10), so unlike the stop path there is no
network transmit hop: the three stages are the strategy decision, the wait for the scheduler
tick that emits, and the CAN write.

A sample is four boundary timestamps on **one** clock domain. That single-domain premise is
not this module's to prove — it is what `backend.reaction_bench.clock`'s trusted
`clockProvenance` attests, and the bench refuses to publish without it. Given comparable
timestamps the three segment durations are consecutive differences and telescope back to the
total, the property a decomposition must hold and `test_latency` checks.

Full distributions, never summary-only: each segment and the total are held as a
`CycleTimeHistogram` (`sim.harness.histogram`, WP-0C-06), which keeps every raw sample and
renders the whole binned histogram. `02b` WP-2C-06 acceptance 1 requires the histogram be
produced and recorded, so the histogram collector is reused rather than a percentile triple
recomputed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from sim.harness.histogram import CycleTimeHistogram


class ReactionSegment(Enum):
    """The three consecutive stages the reaction path is decomposed into.

    Ordered as they occur in time: once detection is confirmed, the reaction strategy is
    selected (`WP-2C-05`), the next scheduler tick turns it into a MIT hold frame, and that
    frame is written to the CAN bus. A reaction-time regression lands in exactly one of
    these, which is why the split is worth carrying.
    """

    SELECT = "select"
    SCHEDULE = "schedule"
    CAN = "can"


# The segment order, fixed so the record and the histograms iterate identically.
SEGMENT_ORDER: tuple[ReactionSegment, ...] = (
    ReactionSegment.SELECT,
    ReactionSegment.SCHEDULE,
    ReactionSegment.CAN,
)


class NonMonotonicSampleError(ValueError):
    """A sample's four boundary timestamps do not increase monotonically.

    A decomposition built from out-of-order timestamps is meaningless — a segment would
    carry a negative duration — so the sample is refused at construction rather than
    silently producing a nonsense split.
    """


@dataclass(frozen=True)
class ReactionSample:
    """One detection-confirm-to-first-reaction-frame event, as four boundary timestamps.

    All four are seconds on a single monotonic clock domain; their comparability is what
    `backend.reaction_bench.clock`'s `clockProvenance` attests, and the bench refuses to
    publish a decomposition whose provenance is absent or names the candump forge. The three
    segment durations are the consecutive differences and telescope to `total`.

    Attributes:
        detection_confirm_at: The tick detection latched confirmed (`WP-2C-04`); the
            path-start boundary the plan names detection-confirm.
        reaction_select_at: The reaction strategy selected and set active (`WP-2C-05`).
        scheduler_write_at: The scheduler tick that called the CAN writer for the first
            reaction MIT frame.
        can_first_byte_at: The first byte of that reaction MIT frame on the bus; the
            path-end boundary the plan names first-reaction-frame-sent.
    """

    detection_confirm_at: float
    reaction_select_at: float
    scheduler_write_at: float
    can_first_byte_at: float

    def __post_init__(self) -> None:
        """Refuse a sample whose boundaries are not monotonically non-decreasing.

        Raises:
            NonMonotonicSampleError: If any boundary precedes the one before it.
        """
        boundaries = (
            self.detection_confirm_at,
            self.reaction_select_at,
            self.scheduler_write_at,
            self.can_first_byte_at,
        )
        for earlier, later in zip(boundaries, boundaries[1:], strict=False):
            if later < earlier:
                raise NonMonotonicSampleError(
                    f"reaction-path boundaries must be monotonic; got {boundaries}"
                )

    def segment_durations(self) -> dict[ReactionSegment, float]:
        """Return the three segment durations, in seconds.

        Returns:
            (dict[ReactionSegment, float]) Each stage's duration; the three sum to `total`.
        """
        return {
            ReactionSegment.SELECT: self.reaction_select_at - self.detection_confirm_at,
            ReactionSegment.SCHEDULE: self.scheduler_write_at - self.reaction_select_at,
            ReactionSegment.CAN: self.can_first_byte_at - self.scheduler_write_at,
        }

    def total(self) -> float:
        """Return the whole detection-confirm-to-CAN-first-byte reaction time, in seconds.

        Returns:
            (float) `can_first_byte_at - detection_confirm_at`.
        """
        return self.can_first_byte_at - self.detection_confirm_at

    def reconciles(self, tolerance_sec: float = 1e-9) -> bool:
        """Whether the three segments sum back to the total within a tolerance.

        The equality is exact in real arithmetic (the segments telescope); the tolerance
        only absorbs floating-point re-association. A sample that fails this is not a
        rounding artifact but a boundary defined wrong.

        Args:
            tolerance_sec: Allowed absolute difference, seconds.

        Returns:
            (bool) True when `sum(segments)` equals `total` within `tolerance_sec`.
        """
        return abs(sum(self.segment_durations().values()) - self.total()) <= tolerance_sec


class ReactionTimeDecomposition:
    """Per-segment and total reaction-time distributions over a set of samples.

    Ownership: holds its own `CycleTimeHistogram` per segment and one for the total, each
    built from an immutable sample copy. The histograms are the full distributions, and
    this object never decides a pass line — the numeric target stays decision-needed
    (`02b` WP-2C-06 acceptance 2).
    """

    def __init__(self, samples: Sequence[ReactionSample]) -> None:
        """Aggregate samples into per-segment and total histograms.

        Args:
            samples: The reaction samples to decompose; may be empty when the real
                measurement is deferred, in which case every distribution is empty rather
                than fabricated.
        """
        self._sample_count = len(samples)
        per_segment: dict[ReactionSegment, list[float]] = {segment: [] for segment in SEGMENT_ORDER}
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

    def segment(self, segment: ReactionSegment) -> CycleTimeHistogram:
        """Return the full distribution of one segment's durations.

        Args:
            segment: The stage to read.

        Returns:
            (CycleTimeHistogram) The segment's distribution.
        """
        return self._segments[segment]

    def total(self) -> CycleTimeHistogram:
        """Return the full distribution of the total reaction time.

        Returns:
            (CycleTimeHistogram) The total reaction-time distribution.
        """
        return self._total

    def as_record(self) -> dict[str, Any]:
        """Serialize the decomposition for the evidence artifact.

        Returns:
            (dict[str, Any]) `sample_count`, one full histogram per segment keyed by its
            name, and the total reaction-time histogram — the histogram WP-2C-06
            acceptance 1 requires be produced and recorded.
        """
        return {
            "sample_count": self._sample_count,
            "segments": {
                segment.value: self._segments[segment].as_record() for segment in SEGMENT_ORDER
            },
            "total": self._total.as_record(),
        }
