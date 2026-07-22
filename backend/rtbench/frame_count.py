"""The `PG-CAN-001` verdict: frames per control cycle, and where the count came from.

`02a` WP-1-04 acceptance ⑧: 32 frames/cycle is pattern B and passes; 16 means the
code path changed or the measurement window is wrong, and downstream must not proceed
until that is root-caused; any other count is an outright error. The rule is simple —
the load-bearing part is *provenance*. A real verdict needs a real `candump` count
from the bus, which does not exist on this host, so a count sourced from the synthetic
model is published as provisional and explicitly not a `PG-CAN-001` pass. Rendering a
model count as a bus measurement is the faked-green `THE ONE RULE` forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.rtbench.constants import (
    FRAME_GATE,
    PATTERN_A_FRAMES_PER_CYCLE,
    PATTERN_B_FRAMES_PER_CYCLE,
)


class FrameCountSource(Enum):
    """Where a frames-per-cycle count came from.

    Only `REAL_CANDUMP` can produce a binding `PG-CAN-001` verdict; `SYNTHETIC_MODEL`
    is the offline placeholder that is always provisional.
    """

    REAL_CANDUMP = "real-candump"
    SYNTHETIC_MODEL = "synthetic-model"


class FrameCountStatus(Enum):
    """The `PG-CAN-001` verdict states.

    `PASS` is 32 (pattern B). `INVESTIGATE` is 16 — a real result that blocks
    downstream until root-caused, not a pass and not an error. `ERROR` is any other
    count. `PROVISIONAL` is any count that came from the synthetic model rather than
    the bus, and is never a binding verdict.
    """

    PASS = "PASS"
    INVESTIGATE = "INVESTIGATE"
    ERROR = "ERROR"
    PROVISIONAL = "PROVISIONAL"


@dataclass(frozen=True)
class PgCan001Verdict:
    """A frames-per-cycle judgment with its provenance.

    Attributes:
        frames_per_cycle: The measured or modelled frame count.
        source: Whether the count came from a real `candump` or the synthetic model.
        status: The verdict state.
        pattern: The inferred loop pattern (`B` for 32, `A` for 16), or None.
        blocks_downstream: Whether downstream work must halt on this verdict.
    """

    frames_per_cycle: int
    source: FrameCountSource
    status: FrameCountStatus
    pattern: str | None
    blocks_downstream: bool

    def as_record(self) -> dict[str, Any]:
        """Serialize the verdict for the artifact.

        Returns:
            (dict[str, Any]) The count, its source and verdict, and — for a synthetic
            count — a note that the binding `PG-CAN-001` verdict is deferred to a real
            `candump` on the rig.
        """
        record: dict[str, Any] = {
            "gate": FRAME_GATE,
            "frames_per_cycle": self.frames_per_cycle,
            "source": self.source.value,
            "status": self.status.value,
            "pattern": self.pattern,
            "blocks_downstream": self.blocks_downstream,
        }
        if self.source is FrameCountSource.SYNTHETIC_MODEL:
            record["note"] = (
                "modelled frame count, not a candump measurement; the binding PG-CAN-001 "
                "verdict comes from a real candump on the rig (deferred)"
            )
        return record


def judge_pg_can_001(frames_per_cycle: int, source: FrameCountSource) -> PgCan001Verdict:
    """Judge a frames-per-cycle count, respecting where it came from.

    A synthetic-model count is always `PROVISIONAL`: it can never stand in for the
    bus measurement, so it is not a pass however plausible its value. A real `candump`
    count is judged: 32 passes as pattern B, 16 blocks downstream for investigation,
    and anything else is an error.

    Args:
        frames_per_cycle: The counted frames per control cycle.
        source: The provenance of the count.

    Returns:
        (PgCan001Verdict) The verdict; provisional whenever the count is modelled.
    """
    if source is FrameCountSource.SYNTHETIC_MODEL:
        pattern = _pattern_for(frames_per_cycle)
        return PgCan001Verdict(
            frames_per_cycle=frames_per_cycle,
            source=source,
            status=FrameCountStatus.PROVISIONAL,
            pattern=pattern,
            blocks_downstream=False,
        )
    if frames_per_cycle == PATTERN_B_FRAMES_PER_CYCLE:
        return PgCan001Verdict(
            frames_per_cycle=frames_per_cycle,
            source=source,
            status=FrameCountStatus.PASS,
            pattern="B",
            blocks_downstream=False,
        )
    if frames_per_cycle == PATTERN_A_FRAMES_PER_CYCLE:
        return PgCan001Verdict(
            frames_per_cycle=frames_per_cycle,
            source=source,
            status=FrameCountStatus.INVESTIGATE,
            pattern="A",
            blocks_downstream=True,
        )
    return PgCan001Verdict(
        frames_per_cycle=frames_per_cycle,
        source=source,
        status=FrameCountStatus.ERROR,
        pattern=None,
        blocks_downstream=True,
    )


def _pattern_for(frames_per_cycle: int) -> str | None:
    """Infer the loop pattern from a frame count, for the modelled record.

    Args:
        frames_per_cycle: The frame count.

    Returns:
        (str | None) `B` for 32, `A` for 16, else None.
    """
    if frames_per_cycle == PATTERN_B_FRAMES_PER_CYCLE:
        return "B"
    if frames_per_cycle == PATTERN_A_FRAMES_PER_CYCLE:
        return "A"
    return None
