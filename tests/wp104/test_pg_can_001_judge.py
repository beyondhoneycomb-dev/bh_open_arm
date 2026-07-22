"""Acceptance ⑧: the PG-CAN-001 frame-count verdict, and provenance over value.

32 is pattern B and passes, 16 blocks downstream for investigation, anything else is
an error — but only for a real candump count. A modelled count is always provisional
and can never stand in for the bus measurement, whatever its value.
"""

from __future__ import annotations

from backend.rtbench.constants import FRAME_GATE
from backend.rtbench.frame_count import (
    FrameCountSource,
    FrameCountStatus,
    judge_pg_can_001,
)


def test_real_32_passes_as_pattern_b() -> None:
    verdict = judge_pg_can_001(32, FrameCountSource.REAL_CANDUMP)
    assert verdict.status is FrameCountStatus.PASS
    assert verdict.pattern == "B"
    assert verdict.blocks_downstream is False


def test_real_16_blocks_downstream_for_investigation() -> None:
    verdict = judge_pg_can_001(16, FrameCountSource.REAL_CANDUMP)
    assert verdict.status is FrameCountStatus.INVESTIGATE
    assert verdict.pattern == "A"
    assert verdict.blocks_downstream is True


def test_real_unexpected_count_is_an_error() -> None:
    verdict = judge_pg_can_001(24, FrameCountSource.REAL_CANDUMP)
    assert verdict.status is FrameCountStatus.ERROR
    assert verdict.pattern is None
    assert verdict.blocks_downstream is True


def test_synthetic_32_is_provisional_not_a_pass() -> None:
    verdict = judge_pg_can_001(32, FrameCountSource.SYNTHETIC_MODEL)
    assert verdict.status is FrameCountStatus.PROVISIONAL
    assert verdict.blocks_downstream is False
    record = verdict.as_record()
    assert record["gate"] == FRAME_GATE
    assert record["source"] == "synthetic-model"
    assert "candump" in record["note"]


def test_synthetic_16_is_provisional_never_investigate() -> None:
    # Provenance dominates the value: a modelled 16 does not trigger the real-16 branch.
    verdict = judge_pg_can_001(16, FrameCountSource.SYNTHETIC_MODEL)
    assert verdict.status is FrameCountStatus.PROVISIONAL
    assert verdict.blocks_downstream is False
