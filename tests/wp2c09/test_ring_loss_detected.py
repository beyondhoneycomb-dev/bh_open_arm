"""Ring loss is detected, never swallowed — the WP-2C-09 negative branch.

An undersized ring cannot hold the pre-event span at the feed rate, so a within-window
sample is dropped. The plan's response is RETRY_WITH_VARIANT (recompute capacity/sample
rate), which is only possible if the loss is *visible*: the dropped count rises, the dump
reports `lossless=False`, and `require_lossless` raises rather than letting a short window
pass as a complete record. The contrast case proves an adequately sized ring loses nothing.
"""

from __future__ import annotations

import pytest

from backend.event_ring import EventCapture, EventRingBuffer, EventRingLossError
from ops.cancel.scheduler import LatchReason
from tests.wp2c09.conftest import DT_SEC, SAMPLE_RATE_HZ, encoded_sample

_PRE_SEC = 2.0
_POST_SEC = 2.0
_EVENT_TICK = 300
_EVENT_AT = _EVENT_TICK * DT_SEC


def _drive(capacity: int) -> tuple[EventRingBuffer, EventCapture]:
    """Feed pre, arm at the event, feed post to completion; return the ring and capture."""
    ring = EventRingBuffer(capacity=capacity, pre_event_sec=_PRE_SEC, post_event_sec=_POST_SEC)
    for tick in range(_EVENT_TICK + 1):
        ring.record(encoded_sample(tick))
    capture = ring.on_safety_event(LatchReason("g", "PASS", "LATCHED", _EVENT_AT))
    tick = _EVENT_TICK + 1
    while not capture.complete:
        ring.record(encoded_sample(tick))
        tick += 1
    return ring, capture


def test_undersized_ring_reports_loss() -> None:
    """A capacity below the pre-event span drops within-window samples and counts them."""
    # The pre window holds ~200 samples at this rate; 10 slots cannot.
    ring, _capture = _drive(capacity=10)

    assert ring.dropped_within_window > 0


def test_lossy_dump_is_flagged_and_refused() -> None:
    """A lossy dump reads `lossless=False` and `require_lossless` raises the negative branch."""
    _ring, capture = _drive(capacity=10)
    dump = capture.dump

    assert not dump.lossless
    with pytest.raises(EventRingLossError):
        dump.require_lossless()


def test_adequately_sized_ring_loses_nothing() -> None:
    """Sized for the pre span plus headroom, the ring drops no within-window sample."""
    ring, capture = _drive(capacity=int(_PRE_SEC * SAMPLE_RATE_HZ) + SAMPLE_RATE_HZ)

    assert ring.dropped_within_window == 0
    assert capture.dump.lossless
