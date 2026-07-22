"""Pack an encoded preview into a single-WebSocket binary frame (WP-3B-06).

One preview frame is one binary WebSocket message on the single realtime channel
(`CTR-WS@v1` D-2). Its identity is the camera frame tag `<slot>:<channel>`, built
through `CTR-WS@v1`'s own `camera_frame_tag` so the preview carries the exact slot
key the CAM registry, the CAP sidecar and the REC feature key use — the same
identifier round-trips across all four surfaces (`CTR-PRIM@v1` join). The tag is
length-prefixed so the opaque image bytes that follow need no delimiter and no
second stream: everything travels as `[uint16 tag length][tag][image bytes]`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from backend.sensing.preview.constants import (
    MAX_TAG_BYTES,
    TAG_LENGTH_PREFIX_BYTES,
    TAG_LENGTH_STRUCT,
)
from backend.sensing.preview.encode import EncodedImage
from contracts.prim import WS_TAG_SEPARATOR, CameraSlotKey, FrameType
from contracts.ws import camera_frame_tag, slot_from_camera_frame_tag


class PreviewFrameError(RuntimeError):
    """Raised when a preview binary frame cannot be built or parsed."""


@dataclass(frozen=True)
class PreviewFrame:
    """One encoded preview ready to send as a single-WS binary frame.

    Attributes:
        slot: The camera identifier the preview belongs to.
        channel: The frame type (RGB or depth) the payload previews.
        content_type: The MIME type a client decodes the payload as.
        payload: The encoded image bytes.
    """

    slot: CameraSlotKey
    channel: FrameType
    content_type: str
    payload: bytes

    @property
    def tag(self) -> str:
        """The `CTR-WS@v1` camera frame tag `<slot>:<channel>` this frame rides under."""
        return camera_frame_tag(self.slot, self.channel)

    def to_ws_binary(self) -> bytes:
        """Pack this frame into its single-WebSocket binary message.

        Returns:
            (bytes) `[uint16 tag length][tag utf-8][image bytes]`.

        Raises:
            PreviewFrameError: If the tag is longer than the length prefix can carry.
        """
        tag_bytes = self.tag.encode("utf-8")
        if len(tag_bytes) > MAX_TAG_BYTES:
            raise PreviewFrameError(
                f"preview tag {self.tag!r} is {len(tag_bytes)} bytes, over {MAX_TAG_BYTES}"
            )
        return struct.pack(TAG_LENGTH_STRUCT, len(tag_bytes)) + tag_bytes + self.payload

    @classmethod
    def from_encoded(cls, slot: CameraSlotKey, encoded: EncodedImage) -> PreviewFrame:
        """Build a preview frame from an encoded image for a camera slot.

        Args:
            slot: The camera identifier the preview belongs to.
            encoded: The encoded RGB/depth payload.

        Returns:
            (PreviewFrame) The frame ready to pack and send.
        """
        return cls(
            slot=slot,
            channel=encoded.channel,
            content_type=encoded.content_type,
            payload=encoded.payload,
        )


@dataclass(frozen=True)
class ParsedPreviewFrame:
    """A preview binary frame recovered from the wire (the round-trip inverse).

    Attributes:
        slot: The camera identifier recovered from the tag.
        channel: The frame type recovered from the tag.
        payload: The encoded image bytes that followed the tag.
    """

    slot: CameraSlotKey
    channel: FrameType
    payload: bytes


def parse_ws_binary(data: bytes) -> ParsedPreviewFrame:
    """Recover a preview frame's slot, channel and image bytes from its WS message.

    Args:
        data: A `to_ws_binary()` message.

    Returns:
        (ParsedPreviewFrame) The slot, channel and payload the message carried.

    Raises:
        PreviewFrameError: If the message is truncated or the tag is malformed.
    """
    if len(data) < TAG_LENGTH_PREFIX_BYTES:
        raise PreviewFrameError("preview frame shorter than its tag-length prefix")
    (tag_len,) = struct.unpack(TAG_LENGTH_STRUCT, data[:TAG_LENGTH_PREFIX_BYTES])
    tag_end = TAG_LENGTH_PREFIX_BYTES + tag_len
    if len(data) < tag_end:
        raise PreviewFrameError("preview frame tag is truncated")
    tag = data[TAG_LENGTH_PREFIX_BYTES:tag_end].decode("utf-8")
    slot = slot_from_camera_frame_tag(tag)
    channel = FrameType(tag.split(WS_TAG_SEPARATOR, 1)[1])
    return ParsedPreviewFrame(slot=slot, channel=channel, payload=data[tag_end:])
