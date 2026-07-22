"""Acceptance ①②: nearest-match pairs within slop; a miss drops, never fabricates.

`02b` §6.2 WP-3B-04: frames pair by nearest capture time within slop, and a slot with
no frame within slop drops — with zero interpolation and zero duplication, because a
fabricated frame is the defect. These tests run against the synthetic camera with
injected jitter (the mandated 3B target) and pin the three structural guarantees:
every matched frame is a real input frame, no frame is used twice, and every set sits
within slop.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.sensing.timesync import (
    DropTally,
    SyncPolicy,
    SyncResult,
    TimedFrame,
    synchronize,
)
from backend.sensing.timesync.constants import NANOS_PER_SECOND
from contracts.capture.schema import capture_match_drop_classification
from contracts.fixtures.synthetic_camera import SyntheticCamera
from contracts.fixtures.synthetic_dataset import default_camera_specs
from contracts.prim import CameraSlotKey, DropClassification
from tests.wp3b04.conftest import configured_spec, spec_fps, timed_frames

_SPECS = default_camera_specs()
_FPS = spec_fps(configured_spec(0))
_PERIOD_NS = NANOS_PER_SECOND // _FPS
_MS_NS = NANOS_PER_SECOND // 1000
_FRAMES = 12


def _policy() -> SyncPolicy:
    return SyncPolicy.for_fps(_FPS)


def _no_fabrication(
    result: SyncResult, streams: Mapping[CameraSlotKey, Sequence[TimedFrame]]
) -> None:
    """Every matched frame is a real input frame; none is synthesised."""
    inputs = {
        (frame.slot, frame.frame_index, frame.match_ts_ns)
        for stream in streams.values()
        for frame in stream
    }
    for matched in result.matched:
        for slot, frame in matched.frames.items():
            assert frame.slot == slot
            assert (frame.slot, frame.frame_index, frame.match_ts_ns) in inputs


def _no_duplication(result: SyncResult, slots: Sequence[CameraSlotKey]) -> None:
    """No slot contributes the same frame index to two matched sets."""
    for slot in slots:
        indices = [matched.frames[slot].frame_index for matched in result.matched]
        assert len(indices) == len(set(indices)), f"slot {slot.value} reused a frame"


def _accounting_closes(
    result: SyncResult, streams: Mapping[CameraSlotKey, Sequence[TimedFrame]]
) -> None:
    """Every input frame is either matched once or dropped once."""
    total = sum(len(stream) for stream in streams.values())
    assert result.matched_frame_count + result.dropped.total == total


def test_constant_offset_pairs_every_frame_within_slop() -> None:
    """A right camera trailing left by 5 ms (< slop) pairs all frames, drops none (①)."""
    left, right = _SPECS[0].slot, _SPECS[1].slot
    streams = {
        left: timed_frames(SyntheticCamera(spec=_SPECS[0], start_mono_ns=0), _FRAMES),
        right: timed_frames(SyntheticCamera(spec=_SPECS[1], start_mono_ns=5 * _MS_NS), _FRAMES),
    }
    policy = _policy()
    result = synchronize(streams, policy)

    assert len(result.matched) == _FRAMES
    assert result.dropped.total == 0
    for matched in result.matched:
        assert matched.spread_ns() <= policy.slop_ns
        assert matched.spread_ns() == 5 * _MS_NS
    _no_fabrication(result, streams)
    _no_duplication(result, (left, right))
    _accounting_closes(result, streams)


def test_within_slop_jitter_is_absorbed_by_nearest_match() -> None:
    """Per-frame jitter under slop still pairs every frame — nearest-match absorbs it (①)."""
    left, right = _SPECS[0].slot, _SPECS[1].slot
    third_ms = (NANOS_PER_SECOND // 1000) * 3
    jitter = {index: (index % 3 - 1) * third_ms for index in range(_FRAMES)}
    streams = {
        left: timed_frames(SyntheticCamera(spec=_SPECS[0], start_mono_ns=0), _FRAMES),
        right: timed_frames(
            SyntheticCamera(spec=_SPECS[1], start_mono_ns=0, jitter_ns=jitter), _FRAMES
        ),
    }
    policy = _policy()
    result = synchronize(streams, policy)

    # Every frame pairs with its true counterpart; the jitter never exceeds slop.
    assert len(result.matched) == _FRAMES
    assert result.dropped.total == 0
    for matched in result.matched:
        assert matched.frames[left].frame_index == matched.frames[right].frame_index
        assert matched.spread_ns() <= policy.slop_ns
    _no_fabrication(result, streams)
    _no_duplication(result, (left, right))
    _accounting_closes(result, streams)


def test_a_dropped_frame_leaves_its_partner_unmatched_and_dropped() -> None:
    """A drop in one stream leaves its counterpart with no within-slop partner (②).

    On a dense grid every timestamp is within slop of *some* frame, so a genuine
    match miss comes from a gap: dropping the left index-5 frame strands the right
    index-5 frame — its nearest left neighbours are a full frame away — and it is
    dropped, never interpolated from the neighbours or duplicated onto another set.
    """
    left, right = _SPECS[0].slot, _SPECS[1].slot
    dropped_index = 5
    streams = {
        left: timed_frames(
            SyntheticCamera(
                spec=_SPECS[0], start_mono_ns=0, dropped_indices=frozenset({dropped_index})
            ),
            _FRAMES,
        ),
        right: timed_frames(SyntheticCamera(spec=_SPECS[1], start_mono_ns=0), _FRAMES),
    }
    policy = _policy()
    result = synchronize(streams, policy)

    # The stranded right frame is dropped, not matched to a neighbour or fabricated.
    right_matched_indices = {matched.frames[right].frame_index for matched in result.matched}
    assert dropped_index not in right_matched_indices
    assert result.dropped.per_slot[right] == 1
    assert result.dropped.per_slot[left] == 0
    assert len(result.matched) == _FRAMES - 1
    for matched in result.matched:
        assert matched.frames[left].frame_index == matched.frames[right].frame_index
        assert matched.spread_ns() <= policy.slop_ns
    _no_fabrication(result, streams)
    _no_duplication(result, (left, right))
    _accounting_closes(result, streams)


def test_a_starved_slot_never_duplicates_its_one_frame() -> None:
    """When one slot has a single frame, at most one set forms — no duplication (②)."""
    left, right = _SPECS[0].slot, _SPECS[1].slot
    # Left streams five frames on the grid; right has exactly one, near the third.
    left_frames = [
        TimedFrame(
            slot=left, frame_index=i, match_ts_ns=i * _PERIOD_NS, capture_ts_ns=i * _PERIOD_NS
        )
        for i in range(5)
    ]
    only = 2 * _PERIOD_NS + 1_000
    right_frames = [TimedFrame(slot=right, frame_index=0, match_ts_ns=only, capture_ts_ns=only)]
    streams = {left: left_frames, right: right_frames}

    result = synchronize(streams, _policy())

    # The single right frame is used at most once — the other four left frames drop.
    assert len(result.matched) == 1
    assert result.matched[0].frames[right].frame_index == 0
    assert result.dropped.per_slot[left] == 4
    assert result.dropped.per_slot[right] == 0
    _accounting_closes(result, streams)


def test_drop_classification_is_the_frozen_capture_match_meaning() -> None:
    """A match drop carries CTR-CAP's COUNTED class, not a redefined one."""
    left, right = _SPECS[0].slot, _SPECS[1].slot
    streams = {
        left: [TimedFrame(slot=left, frame_index=0, match_ts_ns=0, capture_ts_ns=0)],
        right: [TimedFrame(slot=right, frame_index=0, match_ts_ns=10**9, capture_ts_ns=10**9)],
    }
    result = synchronize(streams, _policy())
    assert isinstance(result.dropped, DropTally)
    assert result.dropped.classification is DropClassification.COUNTED
    assert result.dropped.classification == capture_match_drop_classification()


def test_a_single_slot_cannot_be_synchronised() -> None:
    """Synchronisation is a cross-slot object; one slot is a usage error."""
    slot = _SPECS[0].slot
    streams = {slot: [TimedFrame(slot=slot, frame_index=0, match_ts_ns=0, capture_ts_ns=0)]}
    try:
        synchronize(streams, _policy())
    except ValueError:
        return
    raise AssertionError("a single-slot synchronise must be rejected")
