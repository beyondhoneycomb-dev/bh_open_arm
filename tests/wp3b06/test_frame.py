"""WP-3B-06 framing: one binary WebSocket message tagged `<slot>:<channel>`.

`02b` §6.2: a preview is a single WS binary frame carrying the camera id plus the
channel tag. The tag is `CTR-WS@v1`'s own `camera_frame_tag`, and the frame packs
and round-trips back to the same slot, channel and image bytes.
"""

from __future__ import annotations

import pytest

from backend.sensing.preview.encode import EncodedImage
from backend.sensing.preview.frame import PreviewFrame, PreviewFrameError, parse_ws_binary
from contracts.prim import CameraSlotKey, FrameType
from contracts.ws import camera_frame_tag, slot_from_camera_frame_tag


def _frame(slot_name: str, channel: FrameType, payload: bytes) -> PreviewFrame:
    slot = CameraSlotKey(slot_name)
    encoded = EncodedImage(
        channel=channel, content_type="image/jpeg", payload=payload, width=4, height=4
    )
    return PreviewFrame.from_encoded(slot, encoded)


def test_tag_is_the_ctr_ws_camera_frame_tag() -> None:
    """The frame tag is built through `CTR-WS@v1`, so it carries the shared slot key."""
    frame = _frame("left_wrist", FrameType.RGB, b"jpegbytes")
    assert frame.tag == camera_frame_tag(CameraSlotKey("left_wrist"), FrameType.RGB)
    assert slot_from_camera_frame_tag(frame.tag) == CameraSlotKey("left_wrist")


def test_binary_frame_round_trips_slot_channel_and_payload() -> None:
    """Packing then parsing recovers the exact slot, channel and image bytes."""
    frame = _frame("right_overhead", FrameType.DEPTH, b"\x89PNG\r\n\x1a\n depth bytes")
    parsed = parse_ws_binary(frame.to_ws_binary())

    assert parsed.slot == CameraSlotKey("right_overhead")
    assert parsed.channel is FrameType.DEPTH
    assert parsed.payload == b"\x89PNG\r\n\x1a\n depth bytes"


def test_a_truncated_binary_frame_is_refused() -> None:
    """A message too short for its declared tag length raises rather than misreads."""
    frame = _frame("front", FrameType.RGB, b"x")
    packed = frame.to_ws_binary()
    with pytest.raises(PreviewFrameError):
        parse_ws_binary(packed[:1])
