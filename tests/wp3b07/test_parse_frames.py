"""Acceptance ① (CG-3B-07a) — newline-JSON frames parse off the synthetic stream.

`FR-TEL-014`: the receiver ingests `:5006` newline-terminated UTF-8 JSON. Every
frozen synthetic sample decodes to per-arm state, several frames packed into one
datagram each parse, and a malformed datagram is rejected rather than corrupting
the stream.
"""

from __future__ import annotations

import json

import pytest

from backend.teleop.vr_udp import VrFrame, parse_datagram, split_frames
from backend.teleop.vr_udp.protocol import FrameParseError
from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from tests.wp3b07._support import datagram, datagram_from_sample, raw_payload


def test_every_synthetic_sample_parses() -> None:
    """The whole synthetic run decodes; each frame carries both arms and both stamps."""
    stream = SyntheticVrPoseStream()
    for index in range(24):
        frame = parse_datagram(datagram_from_sample(stream, index), receive_mono_ns=1_000 + index)
        assert isinstance(frame, VrFrame)
        assert set(frame.arms) == {"left", "right"}
        assert frame.source_ts == pytest.approx(stream.sample(index).teleop_sample.source_ts)
        assert frame.receive_mono_ns == 1_000 + index


def test_grip_and_buttons_are_carried_through() -> None:
    """Analog grip and face buttons decode as-is (the clutch/UI inputs downstream)."""
    payload = raw_payload(left_grip=0.3, right_grip=0.9)
    payload["a"] = True
    payload["y"] = True
    frame = parse_datagram(datagram(payload), receive_mono_ns=7)
    assert frame.arm("left").grip == pytest.approx(0.3)
    assert frame.arm("right").grip == pytest.approx(0.9)
    assert frame.buttons["a"] is True
    assert frame.buttons["b"] is False
    assert frame.buttons["y"] is True


def test_multiple_frames_in_one_datagram_split() -> None:
    """A datagram carrying several newline-terminated frames splits into each one."""
    stream = SyntheticVrPoseStream()
    packed = b"".join(datagram_from_sample(stream, index) for index in range(3))
    segments = split_frames(packed)
    assert len(segments) == 3
    frames = [
        parse_datagram(segment, receive_mono_ns=index) for index, segment in enumerate(segments)
    ]
    assert [f.source_ts for f in frames] == [
        pytest.approx(stream.sample(i).teleop_sample.source_ts) for i in range(3)
    ]


def test_blank_segments_are_dropped() -> None:
    """Empty segments between/after newlines are not parsed as frames."""
    assert split_frames(b"\n\n") == []
    assert split_frames(b"   \n") == []


@pytest.mark.parametrize(
    "bad",
    [
        b"not json at all\n",
        b"[1, 2, 3]\n",  # a JSON array, not an object
        b"\xff\xfe\x00\n",  # not valid UTF-8
    ],
)
def test_malformed_datagram_rejected(bad: bytes) -> None:
    """A non-JSON / non-object / non-UTF-8 datagram raises rather than parsing."""
    with pytest.raises(FrameParseError):
        parse_datagram(bad, receive_mono_ns=1)


def test_missing_required_key_rejected() -> None:
    """A frame missing a required pose/validity key is rejected."""
    payload = raw_payload()
    del payload["lc"]
    with pytest.raises(FrameParseError):
        parse_datagram(datagram(payload), receive_mono_ns=1)


def test_non_finite_component_rejected() -> None:
    """A NaN/inf pose component is a corrupt datagram, not a pose."""
    payload = raw_payload()
    # json.dumps emits bare NaN/Infinity tokens the receiver's json.loads accepts.
    raw = json.dumps(payload).replace("[0.1, 0.0, 0.0]", "[NaN, 0.0, 0.0]")
    with pytest.raises(FrameParseError):
        parse_datagram((raw + "\n").encode("utf-8"), receive_mono_ns=1)
