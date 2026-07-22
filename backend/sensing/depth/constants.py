"""Named domain tokens for the RealSense depth path (WP-3B-03, `06` §2.4).

The quantisation figures are deliberately absent here. `depth_min`, `depth_max`,
`shift`, `use_log`, the 12-bit quantum ceiling and the pixel format are the frozen
LeRobot v0.6.0 `DepthEncoderConfig` values; `encoding.py` imports them from
`lerobot.configs.video` at the one place they are used, so this platform owns no
second copy of the encoder grid (`06` §2.4). What lives here is what the platform
does own: the no-measurement sentinel, the class allowed to emit depth, and the
method names by which the v0.6.0 depth API is recognised.
"""

from __future__ import annotations

# A depth pixel of 0 mm means "no measurement available", never "zero distance"
# (`06` §2.4, FR-CAM-038: RealSense depth is uint16 mm, pixel 0 = no measurement).
# The lossy log encoder does not preserve this sentinel, so it is the fill-rate and
# invalid-mask carrier — named here rather than written as a bare 0 at each site.
DEPTH_NO_MEASUREMENT_MM = 0

# LeRobot's only camera class that emits a depth key is the RealSense one, whose
# draccus type name is `intelrealsense` (`06` §2.5, FR-CAM-038: the depth-emitting
# class is intelrealsense alone). A depth toggle on any other class is a
# configuration error.
REALSENSE_TYPE_NAME = "intelrealsense"

# The two methods whose presence *is* the v0.6.0 depth gate (`06` §2.4): 0.5.1 ships
# neither (depth only via synchronous `read_depth`), v0.6.0 adds both for the
# record/preview path. The gate is judged on these names, never on a parsed version
# string (FR-CAM-083, `02b` §6.2 WP-3B-03 ①).
DEPTH_ASYNC_READ_METHOD = "async_read_depth"
DEPTH_LATEST_READ_METHOD = "read_latest_depth"
