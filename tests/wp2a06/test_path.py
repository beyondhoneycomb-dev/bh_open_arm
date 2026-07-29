"""Acceptance ①: the four-stage stop-path shape is declared and its anchors still resolve.

The shape is only worth publishing if it describes the code that exists, so these check
both halves: the declaration says what `02b` WP-2A-06 says it says, and every stage anchor
imports. The second half is the one that bites — a stage anchored to a symbol somebody
renamed is a stop path that changed shape without anyone noticing, and the fixture below
proves the check catches exactly that rather than passing on a string comparison.

Resolving is not enough on its own: every anchor is an importable symbol, so a declaration
pointed at the wrong one still resolves. Each stage is therefore checked against the symbol
the plan says owns its boundary, not merely against something that imports.
"""

from __future__ import annotations

import pytest

from backend.actuation import ActuationScheduler, CanWriter
from backend.deadman import DeadmanLease, DeadmanMonitor
from backend.stopbench import (
    SEGMENT_ORDER,
    STOP_PATH,
    StopPathAnchorMissingError,
    StopPathSegment,
    StopPathStage,
    assert_anchors_resolve,
    path_record,
)


def test_segment_order_is_the_four_named_stages() -> None:
    assert SEGMENT_ORDER == (
        StopPathSegment.HARNESS_EVENT,
        StopPathSegment.TRANSMIT,
        StopPathSegment.SCHEDULER,
        StopPathSegment.CAN,
    )


def test_every_declared_anchor_resolves() -> None:
    assert assert_anchors_resolve() == STOP_PATH


def test_stage_anchors_are_the_real_lease_monitor_scheduler_and_write_symbols() -> None:
    resolved = [stage.resolve() for stage in STOP_PATH]
    assert resolved == [DeadmanLease, DeadmanMonitor, ActuationScheduler, CanWriter]


def test_each_stage_anchors_the_symbol_that_owns_its_boundary() -> None:
    # The pairing, not just the set: WP-2A-06's declared input from WP-2A-02 is the lease's
    # expiry, and the path ends at the single CAN writer. A stage holding the right symbol
    # under the wrong segment is a stop path declared in the wrong order.
    assert {stage.segment: stage.resolve() for stage in STOP_PATH} == {
        StopPathSegment.HARNESS_EVENT: DeadmanLease,
        StopPathSegment.TRANSMIT: DeadmanMonitor,
        StopPathSegment.SCHEDULER: ActuationScheduler,
        StopPathSegment.CAN: CanWriter,
    }


def test_a_vanished_anchor_symbol_is_refused() -> None:
    vanished = StopPathStage(
        segment=StopPathSegment.SCHEDULER,
        opens_at="a boundary whose owner was renamed away",
        anchor="backend.actuation:RenamedAwayScheduler",
        owner_wp="WP-1-03",
    )
    with pytest.raises(StopPathAnchorMissingError):
        assert_anchors_resolve((vanished,))


def test_a_vanished_anchor_module_is_refused() -> None:
    vanished = StopPathStage(
        segment=StopPathSegment.TRANSMIT,
        opens_at="a boundary whose owning package was deleted",
        anchor="backend.deleted_package:Anything",
        owner_wp="WP-2A-02",
    )
    with pytest.raises(StopPathAnchorMissingError):
        assert_anchors_resolve((vanished,))


def test_record_carries_the_shape_and_no_durations() -> None:
    record = path_record()
    assert record["stage_count"] == 4
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
