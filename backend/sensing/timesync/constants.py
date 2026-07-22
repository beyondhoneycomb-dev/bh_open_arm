"""Named reference values for the time-synchroniser (`02b` §6 WP-3B-04, `06` §2.6).

The magnitudes here are units and librealsense option codes, not acceptance
targets. The slop *floor* is derived from a stream's fps rather than fixed, so it
lives as a function in `policy`, not as a literal here; the only phase figure kept
as a constant is the 30 fps reference, and it is imported from the camera harness
so the half-frame bound has one definition (`backend.camera.constants`).
"""

from __future__ import annotations

from backend.camera.constants import NANOSECONDS_PER_MILLISECOND

# Seconds decompose into these so nanoseconds-per-second is derived from the shared
# millisecond magnitude rather than restated as a second bare 1e9 literal.
MILLISECONDS_PER_SECOND = 1000
NANOS_PER_SECOND = MILLISECONDS_PER_SECOND * NANOSECONDS_PER_MILLISECOND

# librealsense `inter_cam_sync_mode` option codes (`06` §2.6, FR-CAM-017/018). A
# free-running camera is 0, the trigger source is 1 (master), a triggered camera is
# 2 (slave). These are the device's own integers, named so the hardware-sync group
# emits the value the driver expects rather than an invented one.
INTER_CAM_SYNC_MODE_DEFAULT = 0
INTER_CAM_SYNC_MODE_MASTER = 1
INTER_CAM_SYNC_MODE_SLAVE = 2
