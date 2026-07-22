"""WP-3B-06 encode: downscale + JPEG for RGB, lossless PNG16 or colormap for depth.

`02b` §6.1/§6.2: a preview frame is downscaled and `cv2.imencode`-d — RGB to JPEG,
depth to a lossless 16-bit PNG or a colormapped JPEG. These run fully (cv2 is
installed): a real frame is encoded and decoded back, and the shapes and the
lossless depth reading are asserted against the decode.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from backend.sensing.preview.constants import PREVIEW_MAX_LONG_EDGE_PX
from backend.sensing.preview.encode import (
    DepthEncoding,
    PreviewEncodeError,
    encode_depth_colormap,
    encode_depth_png16,
    encode_frame,
    encode_rgb,
    target_size,
)
from contracts.prim import FrameType
from tests.wp3b06.support import make_camera


def test_target_size_never_upscales() -> None:
    """A frame already within the long-edge target is left unscaled."""
    assert target_size(320, 240, PREVIEW_MAX_LONG_EDGE_PX) == (320, 240)


def test_target_size_downscales_preserving_aspect() -> None:
    """A frame over the target shrinks so its longest edge meets the cap."""
    assert target_size(1280, 720, 640) == (640, 360)


def test_rgb_encodes_to_a_decodable_downscaled_jpeg() -> None:
    """An oversized RGB frame downscales and encodes to a JPEG a client can decode (①)."""
    frame = make_camera("front", FrameType.RGB, width=1280, height=720).read(0)
    assert frame is not None
    encoded = encode_rgb(frame, max_long_edge=640, jpeg_quality=80)

    assert encoded.channel is FrameType.RGB
    assert encoded.content_type == "image/jpeg"
    assert (encoded.width, encoded.height) == (640, 360)
    decoded = cv2.imdecode(np.frombuffer(encoded.payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (360, 640, 3)


def test_depth_png16_round_trips_the_millimetre_reading_losslessly() -> None:
    """Depth-as-PNG16 preserves the exact 16-bit value when no downscale applies."""
    frame = make_camera("wrist_depth", FrameType.DEPTH, width=8, height=8).read(0)
    assert frame is not None
    encoded = encode_depth_png16(frame, max_long_edge=PREVIEW_MAX_LONG_EDGE_PX)

    assert encoded.content_type == "image/png"
    decoded = cv2.imdecode(np.frombuffer(encoded.payload, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    expected = np.frombuffer(frame.data, dtype=np.uint16).reshape((8, 8))
    assert decoded.dtype == np.uint16
    assert np.array_equal(decoded, expected)


def test_depth_colormap_encodes_to_a_three_channel_jpeg() -> None:
    """Depth-as-colormap is a legible JPEG, no longer a millimetre reading."""
    frame = make_camera("wrist_depth", FrameType.DEPTH, width=16, height=16).read(0)
    assert frame is not None
    encoded = encode_depth_colormap(frame, max_long_edge=PREVIEW_MAX_LONG_EDGE_PX, jpeg_quality=80)

    assert encoded.content_type == "image/jpeg"
    decoded = cv2.imdecode(np.frombuffer(encoded.payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (16, 16, 3)


def test_encode_frame_dispatches_on_channel_and_depth_mode() -> None:
    """`encode_frame` routes RGB to JPEG and depth to the selected depth encoding."""
    rgb = make_camera("front", FrameType.RGB).read(0)
    depth = make_camera("wrist_depth", FrameType.DEPTH).read(0)
    assert rgb is not None and depth is not None

    rgb_out = encode_frame(rgb, 640, 80, DepthEncoding.COLORMAP)
    png_out = encode_frame(depth, 640, 80, DepthEncoding.PNG16)
    cmap_out = encode_frame(depth, 640, 80, DepthEncoding.COLORMAP)

    assert rgb_out.content_type == "image/jpeg"
    assert png_out.content_type == "image/png"
    assert cmap_out.content_type == "image/jpeg"


def test_a_byte_count_that_disagrees_with_geometry_is_refused() -> None:
    """A buffer whose length does not match the declared geometry raises, not corrupts."""

    class BadFrame:
        slot = make_camera("front").slot
        frame_type = FrameType.RGB
        width = 8
        height = 8
        data = b"\x00\x00\x00"

    with pytest.raises(PreviewEncodeError):
        encode_rgb(BadFrame(), max_long_edge=640, jpeg_quality=80)
