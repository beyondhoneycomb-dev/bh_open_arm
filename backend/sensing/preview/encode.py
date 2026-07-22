"""Downscale + encode a grabbed frame into a preview payload (WP-3B-06).

RGB previews as a downscaled JPEG; depth previews either as a lossless 16-bit PNG
(the millimetre reading survives) or as a colormapped JPEG for a human view
(`02b` §6.1/§6.2 "뎁스 = 16-bit PNG 또는 컬러맵"). The channel count and dtype of
the raw buffer are read from `CTR-PRIM@v1` (`FRAME_TYPE_CHANNELS`/
`FRAME_TYPE_DTYPE`) so this layer never restates what an RGB or depth frame is.

Two deliberate interpolation choices: RGB downscales with `INTER_AREA` (the right
filter for shrinking a photo), depth with `INTER_NEAREST` — averaging depth would
invent millimetre readings between real samples and would blend the `0` = "no
measurement" sentinel into valid neighbours, so depth keeps real samples only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import cv2
import numpy as np

from backend.sensing.preview.constants import (
    DEPTH_COLORMAP,
    DEPTH_COLORMAP_MAX,
    DEPTH_COLORMAP_MIN,
    JPEG_EXT,
    MIME_JPEG,
    MIME_PNG,
    PNG_COMPRESSION_DEFAULT,
    PNG_EXT,
)
from backend.sensing.preview.source import PreviewSourceFrame
from contracts.prim import FRAME_TYPE_CHANNELS, FRAME_TYPE_DTYPE, FrameType


class PreviewEncodeError(RuntimeError):
    """Raised when a frame cannot be reshaped or `cv2.imencode` refuses it."""


class DepthEncoding(StrEnum):
    """How a depth frame is previewed (`02b` §6.1/§6.2 "16-bit PNG 또는 컬러맵").

    `PNG16` keeps the lossless 16-bit millimetre reading; `COLORMAP` trades the
    reading for a legible human view. RGB is unaffected — it is always a JPEG.
    """

    PNG16 = "png16"
    COLORMAP = "colormap"


@dataclass(frozen=True)
class EncodedImage:
    """One encoded preview image: the wire bytes plus what they are.

    Attributes:
        channel: The frame type these bytes preview (RGB or depth).
        content_type: The MIME type a client decodes the payload as.
        payload: The encoded image bytes (JPEG, or 16-bit PNG for lossless depth).
        width: The encoded (downscaled) width in pixels.
        height: The encoded (downscaled) height in pixels.
    """

    channel: FrameType
    content_type: str
    payload: bytes
    width: int
    height: int


def target_size(width: int, height: int, max_long_edge: int) -> tuple[int, int]:
    """Return the downscaled `(width, height)`, never upscaling.

    Args:
        width: Source width in pixels.
        height: Source height in pixels.
        max_long_edge: The longest edge the preview is allowed to reach.

    Returns:
        (tuple[int, int]) The target size; the source size when it already fits.
    """
    longest = max(width, height)
    if longest <= max_long_edge:
        return width, height
    scale = max_long_edge / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def _as_array(frame: PreviewSourceFrame) -> np.ndarray:
    """Reshape a raw frame buffer into an image array, per its `CTR-PRIM@v1` shape.

    Args:
        frame: The grabbed frame carrying raw pixel bytes.

    Returns:
        (np.ndarray) `(H, W, 3)` uint8 for RGB, `(H, W)` uint16 for depth.

    Raises:
        PreviewEncodeError: If the byte count does not match the declared geometry.
    """
    channels = FRAME_TYPE_CHANNELS[frame.frame_type]
    dtype = np.dtype(FRAME_TYPE_DTYPE[frame.frame_type])
    expected = frame.width * frame.height * channels * dtype.itemsize
    if len(frame.data) != expected:
        raise PreviewEncodeError(
            f"frame {frame.slot.value!r} {frame.frame_type.value} has {len(frame.data)} bytes; "
            f"{frame.width}x{frame.height}x{channels}x{dtype.itemsize} needs {expected}"
        )
    flat = np.frombuffer(frame.data, dtype=dtype)
    if channels == 1:
        return flat.reshape((frame.height, frame.width))
    return flat.reshape((frame.height, frame.width, channels))


def _imencode(ext: str, image: np.ndarray, params: list[int]) -> bytes:
    """Encode an array with `cv2.imencode`, raising on the failure return.

    Args:
        ext: The OpenCV format selector (`.jpg`/`.png`).
        image: The array to encode.
        params: The `IMWRITE_*` parameter list.

    Returns:
        (bytes) The encoded image bytes.

    Raises:
        PreviewEncodeError: If OpenCV reports an encode failure.
    """
    ok, buffer = cv2.imencode(ext, image, params)
    if not ok:
        raise PreviewEncodeError(f"cv2.imencode({ext!r}) failed")
    return buffer.tobytes()


def encode_rgb(frame: PreviewSourceFrame, max_long_edge: int, jpeg_quality: int) -> EncodedImage:
    """Downscale an RGB frame and encode it as a preview JPEG.

    The source is RGB (`CTR-PRIM@v1`); OpenCV encodes in BGR order, so the channels
    are swapped before encoding to keep a browser-decoded preview true-colour.

    Args:
        frame: The RGB source frame.
        max_long_edge: The longest edge the preview may reach.
        jpeg_quality: libjpeg quality (0..100).

    Returns:
        (EncodedImage) The JPEG preview payload.
    """
    rgb = _as_array(frame)
    new_width, new_height = target_size(frame.width, frame.height, max_long_edge)
    if (new_width, new_height) != (frame.width, frame.height):
        rgb = cv2.resize(rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    payload = _imencode(JPEG_EXT, bgr, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    return EncodedImage(FrameType.RGB, MIME_JPEG, payload, new_width, new_height)


def encode_depth_png16(frame: PreviewSourceFrame, max_long_edge: int) -> EncodedImage:
    """Downscale a depth frame and encode it as a lossless 16-bit PNG.

    Depth downscales nearest-neighbour so real millimetre samples (and the `0`
    "no measurement" sentinel) are preserved, and PNG keeps the 16-bit value
    lossless, so a client reads back true millimetres.

    Args:
        frame: The depth source frame.
        max_long_edge: The longest edge the preview may reach.

    Returns:
        (EncodedImage) The 16-bit-PNG depth payload.
    """
    depth = _as_array(frame)
    new_width, new_height = target_size(frame.width, frame.height, max_long_edge)
    if (new_width, new_height) != (frame.width, frame.height):
        depth = cv2.resize(depth, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
    payload = _imencode(PNG_EXT, depth, [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION_DEFAULT])
    return EncodedImage(FrameType.DEPTH, MIME_PNG, payload, new_width, new_height)


def encode_depth_colormap(
    frame: PreviewSourceFrame, max_long_edge: int, jpeg_quality: int
) -> EncodedImage:
    """Downscale a depth frame, colourise it, and encode a preview JPEG.

    This is the human-view depth preview: the 16-bit range is normalised to 8 bits
    and a colormap applied, so it is legible but no longer a millimetre reading.

    Args:
        frame: The depth source frame.
        max_long_edge: The longest edge the preview may reach.
        jpeg_quality: libjpeg quality (0..100).

    Returns:
        (EncodedImage) The colormapped JPEG depth payload.
    """
    depth = _as_array(frame)
    new_width, new_height = target_size(frame.width, frame.height, max_long_edge)
    if (new_width, new_height) != (frame.width, frame.height):
        depth = cv2.resize(depth, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
    normalized = cv2.normalize(
        depth, None, DEPTH_COLORMAP_MIN, DEPTH_COLORMAP_MAX, cv2.NORM_MINMAX
    ).astype(np.uint8)
    coloured = cv2.applyColorMap(normalized, DEPTH_COLORMAP)
    payload = _imencode(JPEG_EXT, coloured, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    return EncodedImage(FrameType.DEPTH, MIME_JPEG, payload, new_width, new_height)


def encode_frame(
    frame: PreviewSourceFrame,
    max_long_edge: int,
    jpeg_quality: int,
    depth_encoding: DepthEncoding,
) -> EncodedImage:
    """Encode a frame to its preview payload, dispatching on its channel.

    Args:
        frame: The RGB or depth source frame.
        max_long_edge: The longest edge the preview may reach.
        jpeg_quality: libjpeg quality (0..100) for JPEG payloads.
        depth_encoding: Whether depth previews as lossless PNG16 or a colormap.

    Returns:
        (EncodedImage) The encoded preview payload.
    """
    if frame.frame_type is FrameType.RGB:
        return encode_rgb(frame, max_long_edge, jpeg_quality)
    if depth_encoding is DepthEncoding.PNG16:
        return encode_depth_png16(frame, max_long_edge)
    return encode_depth_colormap(frame, max_long_edge, jpeg_quality)
