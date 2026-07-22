"""Acceptance ① (CG-2C-09a) — a collision event dumps 8 joints × 8 channels × ≥2 s losslessly.

A synthetic stream is fed at a fixed rate, a collision event is armed mid-stream, and
the post window is filled. The dump must carry the full pre and post windows with every
joint and channel present, and — because each cell encodes its own coordinate — every
value must survive intact, so the claim is "no sample lost or corrupted", not merely a
count that happens to match.
"""

from __future__ import annotations

from backend.event_ring import (
    CHANNEL_COUNT,
    EVENT_JOINT_COUNT,
    EventCapture,
    EventRingBuffer,
)
from ops.cancel.scheduler import LatchReason
from tests.wp2c09.conftest import DT_SEC, SAMPLE_RATE_HZ, encoded_sample

_PRE_SEC = 2.0
_POST_SEC = 2.0
_EVENT_TICK = 300
_EVENT_AT = _EVENT_TICK * DT_SEC


def _capacity_for(window_sec: float) -> int:
    """A capacity comfortably larger than the pre window holds at the sample rate."""
    return int(window_sec * SAMPLE_RATE_HZ) + SAMPLE_RATE_HZ


def _run_event() -> EventCapture:
    """Feed pre, arm the event at `_EVENT_AT`, then feed post until the capture completes."""
    ring = EventRingBuffer(
        capacity=_capacity_for(_PRE_SEC),
        pre_event_sec=_PRE_SEC,
        post_event_sec=_POST_SEC,
    )
    for tick in range(_EVENT_TICK + 1):
        ring.record(encoded_sample(tick))
    capture = ring.on_safety_event(
        LatchReason("COLLISION_GUARD:collision_residual", "PASS", "LATCHED", _EVENT_AT)
    )
    tick = _EVENT_TICK + 1
    while not capture.complete:
        ring.record(encoded_sample(tick))
        tick += 1
    return capture


def test_dump_covers_at_least_two_seconds_each_side() -> None:
    """The pre and post windows each span at least the configured two seconds (①)."""
    dump = _run_event().dump

    # Coverage measured from the event is the real guarantee: the pre window reaches
    # back at least _PRE_SEC before the event, the post window reaches _POST_SEC past it.
    assert _EVENT_AT - dump.pre[0].at >= _PRE_SEC
    assert dump.pre[-1].at <= _EVENT_AT
    assert dump.post[-1].at - _EVENT_AT >= _POST_SEC
    # The internal span is one sample period short of the window on the post side (the
    # first post sample lands one tick after the event); allow that plus float slack.
    assert dump.pre_span_sec() >= _PRE_SEC - DT_SEC - 1e-9
    assert dump.post_span_sec() >= _POST_SEC - DT_SEC - 1e-9


def test_dump_carries_all_eight_joints_and_eight_channels() -> None:
    """Every dumped sample carries the full 8-joint × 8-channel matrix (①)."""
    dump = _run_event().dump

    assert CHANNEL_COUNT == 8
    assert EVENT_JOINT_COUNT == 8
    for sample in dump.samples:
        assert len(sample.rows) == EVENT_JOINT_COUNT
        assert all(len(row) == CHANNEL_COUNT for row in sample.rows)


def test_dump_is_lossless_and_uncorrupted() -> None:
    """Every sample in the window is present exactly once and byte-for-byte intact (①)."""
    capture = _run_event()
    dump = capture.dump

    assert dump.lossless
    assert dump.dropped_within_window == 0

    # The window is ticks 100..500 with no gap and no duplication: pre [1.0, 3.0],
    # post (3.0, 5.0]. Reconstruct each tick from `at` and compare the whole matrix.
    ats = [sample.at for sample in dump.samples]
    ticks = [round(at / DT_SEC) for at in ats]
    assert ticks == list(range(100, 501))
    for sample, tick in zip(dump.samples, ticks, strict=True):
        assert sample.rows == encoded_sample(tick).rows


def test_snapshot_is_non_destructive() -> None:
    """Arming a second event after the first still sees the retained pre window (①)."""
    ring = EventRingBuffer(
        capacity=_capacity_for(_PRE_SEC), pre_event_sec=_PRE_SEC, post_event_sec=_POST_SEC
    )
    for tick in range(_EVENT_TICK + 1):
        ring.record(encoded_sample(tick))

    first = ring.on_safety_event(LatchReason("g", "PASS", "LATCHED", _EVENT_AT))
    second = ring.on_safety_event(LatchReason("g", "PASS", "LATCHED", _EVENT_AT))

    assert first.dump.pre == second.dump.pre
    assert len(first.dump.pre) > 0
