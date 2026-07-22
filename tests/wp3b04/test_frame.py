"""Frozen contract: matching basis is sensor-timestamp-if-present, else capture_ts.

`02b` §6.2 WP-3B-04 pins the basis — the device sensor clock when the frame carries
one, else the host grab-time capture_ts — and always preserves the grab instant
beside it. These tests pin both halves against `CTR-CAP@v1` slot captures.
"""

from __future__ import annotations

from backend.sensing.timesync.frame import match_timestamp, timed_from_capture
from backend.sensing.timesync.policy import SyncPolicy
from contracts.capture.schema import CaptureTimestamp, SensorSample, SlotCapture
from tests.wp3b04.conftest import configured_spec, spec_fps

_SLOT = configured_spec(0).slot
_POLICY = SyncPolicy.for_fps(spec_fps(configured_spec(0)))


def test_a_capture_without_a_sensor_matches_on_capture_ts() -> None:
    """A plain webcam frame (no sensor clock) matches on its grab-time capture_ts."""
    capture = SlotCapture(capture_ts=CaptureTimestamp(mono_ns=7_000), sensor=None)
    assert match_timestamp(capture, _POLICY) == 7_000


def test_a_capture_with_a_sensor_matches_on_the_sensor_clock() -> None:
    """A RealSense frame matches on its hardware timestamp, not the host stamp."""
    capture = SlotCapture(
        capture_ts=CaptureTimestamp(mono_ns=7_000),
        sensor=SensorSample(sensor_ts_ns=6_500, frame_number=42),
    )
    assert match_timestamp(capture, _POLICY) == 6_500


def test_a_sensor_without_a_timestamp_falls_back_to_capture_ts() -> None:
    """A device exposing only a frame counter still matches on capture_ts."""
    capture = SlotCapture(
        capture_ts=CaptureTimestamp(mono_ns=7_000),
        sensor=SensorSample(sensor_ts_ns=None, frame_number=42),
    )
    assert match_timestamp(capture, _POLICY) == 7_000


def test_timed_from_capture_preserves_the_grab_instant_beside_the_basis() -> None:
    """The built frame matches on the sensor clock yet keeps the grab capture_ts."""
    capture = SlotCapture(
        capture_ts=CaptureTimestamp(mono_ns=7_000),
        sensor=SensorSample(sensor_ts_ns=6_500, frame_number=42),
    )
    timed = timed_from_capture(_SLOT, 3, capture, _POLICY)
    assert timed.slot == _SLOT
    assert timed.frame_index == 3
    assert timed.match_ts_ns == 6_500
    assert timed.capture_ts_ns == 7_000


def test_a_negative_frame_index_is_rejected() -> None:
    """A frame index below zero is not a valid join key."""
    try:
        timed_from_capture(_SLOT, -1, SlotCapture(CaptureTimestamp(mono_ns=0), None), _POLICY)
    except ValueError:
        return
    raise AssertionError("a negative frame index must be rejected")
