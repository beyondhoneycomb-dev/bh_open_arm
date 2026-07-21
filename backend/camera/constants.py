"""Named reference values for the camera enumerate/measure harness (`06` §2.9/§2.6).

Every value here is a domain quantity the specification cites, named so it lives in
one place. Two of them carry a deliberate caveat: the effective USB3 cap and the
half-frame phase bound are *reference* figures, not confirmed acceptance targets —
`PG-CAM-001` is decided only after real cameras are observed (`02a` WP-0B-08 ⑨). The
calculators therefore take thresholds as parameters and default to these; a green
here never means a configuration cleared a nailed-down target.
"""

from __future__ import annotations

# Bandwidth formula factors (`06` §2.9: Mbps = W × H × Bpp × 8 × fps / 1e6).
BITS_PER_BYTE = 8
MEGABIT_DIVISOR = 1_000_000

# Bytes-per-pixel of the negotiated pixel format, not of "a camera". `06` §2.9 gives
# three worked examples that only reconcile when Bpp is per-format: YUYV/RGB8 packed
# and z16 depth are 2 Bpp, while unpacked RGB888 is 3 Bpp (the 1280×720 "> 660 Mbps"
# figure). Bpp is thus a profile field; these names are what the fixtures build from.
BPP_YUYV = 2
BPP_Z16_DEPTH = 2
BPP_RGB888 = 3

# Lower edge of the 3200–3600 Mbps USB3 *effective* band (`06` NFR-CAM-004). A default
# for the block calculator, never a frozen target — the caller supplies the cap, and
# the binding figure stays provisional until `PG-CAM-001` runs on real hardware.
USB3_EFFECTIVE_CAP_MBPS_REFERENCE = 3200

# Arithmetic maximum exposure-phase offset between two un-hardware-synced cameras at
# 30 fps: half a 33.3 ms frame interval (`06` §2.6). It is the *upper bound* of the
# phase difference, explicitly not a slop floor (`06` FR-CAM-020) — recorded for the
# sync-slop report's context, not asserted as a pass line.
HALF_FRAME_PHASE_MAX_MS_30FPS = 16.7

# Drop-rate bands (`06` NFR-CAM-003): "~2% expected", "~5% overloaded". Reference
# fractions for classifying a computed drop rate, not a gate that runs here.
DROP_WARN_FRACTION = 0.02
DROP_DISCARD_FRACTION = 0.05

# Time-unit conversions for the sync-slop computer (capture_ts is nanoseconds,
# `06` FR-CAM-014; the report speaks milliseconds).
NANOSECONDS_PER_MILLISECOND = 1_000_000
DEFAULT_SLOP_BIN_WIDTH_MS = 1.0
