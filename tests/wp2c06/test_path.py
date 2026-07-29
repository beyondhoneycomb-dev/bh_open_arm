"""Acceptance ①: the three-stage reaction-path shape is declared and its anchors resolve.

The shape is only worth publishing if it describes the code that exists, so these check
both halves: the declaration says what the reaction path is, and every stage anchor
imports. The second half is the one that bites — a stage anchored to a symbol somebody
renamed is a reaction path that changed shape without anyone noticing, and the fixture
below proves the check catches exactly that rather than passing on a string comparison.

The anchors also carry the same-process claim (`02b` WP-2C-10): confirm, select and write
all resolve inside one interpreter, so the path has no network hop to account for.
"""

from __future__ import annotations

import pytest

from backend.actuation import CanWriter
from backend.reaction import ReactionPolicy
from backend.reaction_bench import (
    REACTION_PATH,
    SEGMENT_ORDER,
    ReactionPathAnchorMissingError,
    ReactionPathStage,
    ReactionSegment,
    assert_anchors_resolve,
    path_record,
)
from backend.threshold import ConfirmHysteresisGate


def test_segment_order_is_the_three_named_stages() -> None:
    assert SEGMENT_ORDER == (
        ReactionSegment.SELECT,
        ReactionSegment.SCHEDULE,
        ReactionSegment.CAN,
    )


def test_every_declared_anchor_resolves() -> None:
    assert assert_anchors_resolve() == REACTION_PATH


def test_stage_anchors_are_the_real_confirm_select_and_write_symbols() -> None:
    resolved = [stage.resolve() for stage in REACTION_PATH]
    assert resolved == [ConfirmHysteresisGate, ReactionPolicy, CanWriter]


def test_a_vanished_anchor_symbol_is_refused() -> None:
    vanished = ReactionPathStage(
        segment=ReactionSegment.SELECT,
        opens_at="a boundary whose owner was renamed away",
        anchor="backend.threshold:RenamedAwayGate",
        owner_wp="WP-2C-04",
    )
    with pytest.raises(ReactionPathAnchorMissingError):
        assert_anchors_resolve((vanished,))


def test_a_vanished_anchor_module_is_refused() -> None:
    vanished = ReactionPathStage(
        segment=ReactionSegment.SCHEDULE,
        opens_at="a boundary whose owning package was deleted",
        anchor="backend.deleted_package:Anything",
        owner_wp="WP-2C-05",
    )
    with pytest.raises(ReactionPathAnchorMissingError):
        assert_anchors_resolve((vanished,))


def test_record_carries_the_shape_and_no_durations() -> None:
    record = path_record()
    assert record["stage_count"] == 3
    assert [stage["segment"] for stage in record["stages"]] == [
        segment.value for segment in SEGMENT_ORDER
    ]
    for stage in record["stages"]:
        assert stage["anchor"]
        assert stage["opens_at"]
    # The shape is a shape: no stage carries a time, and the record says so rather than
    # leaving a reader to wonder whether a duration field was dropped.
    assert record["durations"] is None
    assert "CAN bus" in record["ends_at"]
