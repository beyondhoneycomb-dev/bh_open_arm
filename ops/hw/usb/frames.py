"""Frames-consumed-per-cycle recorder and the `PG-CAN-001` classifier.

`15` NFR-PRF-046 requires the M-1 harness to additionally count, per control cycle,
how many CAN frames `recv_all` consumed; `WP-0B-06` acceptance ⑤ feeds that count
into `PG-CAN-001`. The plan's gate reads (`03` §2.1 / `01` NFR-SYS-002): 32 frames
per cycle is pattern B running normally (8 command + 8 refresh, both arms); 16 is
either a deliberate pattern-A code path or a truncated measurement window, and
`PG-CAN-001` blocks downstream work until the cause is named.

This module records the per-cycle counts and renders that verdict. It measures
nothing itself — the counts arrive already parsed from the tool output — so it runs
identically on synthetic fixtures and real captures.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

# The two frame-per-cycle populations `PG-CAN-001` distinguishes (`03` §2.1).
PATTERN_B_FRAMES = 32
PATTERN_A_FRAMES = 16


class FrameVerdict(StrEnum):
    """The `PG-CAN-001` classification of a measured frames-per-cycle mode.

    PG-CAN-001 is a verification gate, not a blocker by itself, but a mode it cannot
    explain must stop downstream progress until the cause is found.
    """

    PATTERN_B_NORMAL = "pattern_b_normal"
    PATTERN_A_OR_WINDOW_ERROR = "pattern_a_or_window_error"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class FramesPerCycle:
    """The measured frames-consumed-per-cycle record and its `PG-CAN-001` verdict.

    Attributes:
        counts: Frames consumed in each recorded cycle, in cycle order.
        mode: The most common per-cycle count — the mode the sweep actually ran at.
        verdict: The `PG-CAN-001` classification of `mode`.
        histogram: count value -> number of cycles that saw it, for provenance.
    """

    counts: tuple[int, ...]
    mode: int | None
    verdict: FrameVerdict
    histogram: dict[int, int]

    def as_dict(self) -> dict[str, object]:
        """Project to a JSON-serialisable mapping for the artifact.

        Returns:
            (dict[str, object]) The record as plain data.
        """
        return {
            "counts": list(self.counts),
            "mode": self.mode,
            "verdict": self.verdict.value,
            "histogram": {str(value): cycles for value, cycles in sorted(self.histogram.items())},
            "pg_can_001_input": self.mode,
        }


def _classify(mode: int | None) -> FrameVerdict:
    """Map a modal frames-per-cycle count to its `PG-CAN-001` verdict.

    Args:
        mode: The dominant per-cycle frame count, or None when no cycles recorded.

    Returns:
        (FrameVerdict) The classification.
    """
    if mode == PATTERN_B_FRAMES:
        return FrameVerdict.PATTERN_B_NORMAL
    if mode == PATTERN_A_FRAMES:
        return FrameVerdict.PATTERN_A_OR_WINDOW_ERROR
    return FrameVerdict.UNEXPECTED


def record_frames_per_cycle(counts: list[int]) -> FramesPerCycle:
    """Record per-cycle consumed-frame counts and classify the dominant mode.

    The mode (most common count), not the mean, is the classification input:
    `PG-CAN-001` asks which discrete pattern the loop ran, and an average of 16s and
    32s would name a mode that never occurred.

    Args:
        counts: Frames consumed in each cycle, in cycle order; may be empty.

    Returns:
        (FramesPerCycle) The record with its `PG-CAN-001` verdict.
    """
    histogram = Counter(counts)
    mode = histogram.most_common(1)[0][0] if histogram else None
    return FramesPerCycle(
        counts=tuple(counts),
        mode=mode,
        verdict=_classify(mode),
        histogram=dict(histogram),
    )
