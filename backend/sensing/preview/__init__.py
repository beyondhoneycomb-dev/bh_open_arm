"""Preview pipe — JPEG-over-WebSocket, read-latest in, TX-only out (WP-3B-06).

The lossy, latest-wins camera preview (`02b` §6.1/§6.2). A frame is read
non-blocking from the camera (`read_latest()` only), downscaled and encoded — RGB
as JPEG, depth as a lossless 16-bit PNG or a colormapped JPEG — and pushed as one
binary frame on the single WebSocket (`CTR-WS@v1`), tagged `<slot>:<channel>`.

Two guarantees are structural, not conventional, and they are the WP's
`FAIL_BLOCKING` boundary (`02b` §6.2): the preview is READ-ONLY on the camera (the
source surface has only a non-blocking `read_latest()`, so it can never stall
capture) and TX-only on the WS (the sink surface can only `send_binary`, so the
preview cannot drive the robot). A dead preview camera warns and skips; it never
fails arm connect or motion. Preview parameters are the pipe's own and change no
recording parameter. Preview OFF stops all encoding and transmission.

This package CONSUMES `CTR-WS@v1` (the camera frame tag, the backpressure rule, the
frame-type class) and `CTR-PRIM@v1` (the camera identifier, the frame-type channel
shape) by reference; it redefines none of them and opens no second realtime stream.
"""

from __future__ import annotations

from backend.sensing.preview.encode import (
    DepthEncoding,
    EncodedImage,
    PreviewEncodeError,
    encode_depth_colormap,
    encode_depth_png16,
    encode_frame,
    encode_rgb,
    target_size,
)
from backend.sensing.preview.frame import (
    ParsedPreviewFrame,
    PreviewFrame,
    PreviewFrameError,
    parse_ws_binary,
)
from backend.sensing.preview.pipe import (
    PreviewConfig,
    PreviewCounters,
    PreviewPipe,
    PreviewService,
)
from backend.sensing.preview.sink import PreviewSink
from backend.sensing.preview.source import LatestFrameSource, PreviewSourceFrame

__all__ = [
    "DepthEncoding",
    "EncodedImage",
    "LatestFrameSource",
    "ParsedPreviewFrame",
    "PreviewConfig",
    "PreviewCounters",
    "PreviewEncodeError",
    "PreviewFrame",
    "PreviewFrameError",
    "PreviewPipe",
    "PreviewService",
    "PreviewSink",
    "PreviewSourceFrame",
    "encode_depth_colormap",
    "encode_depth_png16",
    "encode_frame",
    "encode_rgb",
    "parse_ws_binary",
    "target_size",
]
