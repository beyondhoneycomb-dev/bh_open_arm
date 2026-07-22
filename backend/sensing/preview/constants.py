"""Named constants for the preview pipe (WP-3B-06).

Every literal the encode/frame/pipe layers key on lives here so a preview default
is changed in one place and never restated at a call site. None of these is a
specification-pinned figure: the preview is a lossy, latest-wins convenience view
(`02b` §6.2 WP-3B-06), so the downscale target and JPEG quality are tunables the
`PreviewConfig` overrides, not thresholds a gate cuts on.
"""

from __future__ import annotations

import cv2

# The preview only ever *downscales*: a frame whose longer edge is already at or
# below this is passed through unscaled (a preview never upscales a camera frame).
# A modest long edge keeps the single-WS binary small enough that a camera flood
# is shed by backpressure rather than delaying the lease (`CTR-WS@v1` §7 HOL).
PREVIEW_MAX_LONG_EDGE_PX = 640

# libjpeg quality for the RGB preview and the colormapped-depth preview (0..100).
# 80 is a legible preview at a fraction of a lossless frame; it is not the archival
# quality — the recording path stores lossless PNG (`WP-3B-05`), never this.
JPEG_QUALITY_DEFAULT = 80
JPEG_QUALITY_MIN = 0
JPEG_QUALITY_MAX = 100

# zlib level for the 16-bit-PNG depth preview (0..9). Depth PNG is lossless in the
# pixel value — the 16-bit millimetre reading survives the encode — so the level
# trades CPU for size only, never precision.
PNG_COMPRESSION_DEFAULT = 3

# The colormap applied when depth is previewed as a colour image rather than as a
# lossless 16-bit PNG. JET spreads the near/far range legibly for a human preview.
DEPTH_COLORMAP = cv2.COLORMAP_JET

# The 8-bit range a colormapped depth frame is normalised into before the colormap.
DEPTH_COLORMAP_MIN = 0
DEPTH_COLORMAP_MAX = 255

# OpenCV encode selectors and the MIME types the browser reads the binary payload as.
JPEG_EXT = ".jpg"
PNG_EXT = ".png"
MIME_JPEG = "image/jpeg"
MIME_PNG = "image/png"

# The single-WS binary layout of a preview frame: a big-endian uint16 tag length,
# then the `<slot>:<channel>` tag bytes (`CTR-WS@v1` camera frame tag), then the
# encoded image bytes. The uint16 prefix is what bounds a tag; a slot key is a
# short snake token, so two bytes never truncate a real tag.
TAG_LENGTH_STRUCT = ">H"
TAG_LENGTH_PREFIX_BYTES = 2
MAX_TAG_BYTES = 0xFFFF
