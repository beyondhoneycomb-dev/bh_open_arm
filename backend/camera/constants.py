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

# V4L2 control names, as `v4l2-ctl -L` spells them. Shared between the declaration and the
# fake that stands in for a device, so a typo cannot make the two agree with each other.
CONTROL_AUTO_EXPOSURE = "auto_exposure"
CONTROL_WHITE_BALANCE_AUTOMATIC = "white_balance_automatic"
CONTROL_EXPOSURE_TIME_ABSOLUTE = "exposure_time_absolute"
CONTROL_GAIN = "gain"
CONTROL_WHITE_BALANCE_TEMPERATURE = "white_balance_temperature"

# What marks a control as the automatic-mode switch guarding another control. Containment
# rather than a suffix test, because `focus_automatic_continuous` carries the word in the
# middle; matching only the tail would let that switch sort after the control it gates.
AUTO_SWITCH_NAME_PREFIX = "auto_"
AUTO_SWITCH_NAME_INFIX = "_automatic"

# Arducam B0495 wrist pair. Reference values in the same sense as the bandwidth cap above:
# measured on a sibling rig running this same model, never on this bench. Exposure, gain and
# white balance are all lighting-dependent, so `PG-CAM-001` re-measures them here before any
# of it is a target. The functions take the declaration as an argument for exactly that reason.
ARDUCAM_AUTO_EXPOSURE_MANUAL = 1
ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF = 0

# The other end of each switch — the automatic mode a camera powers up in, and what holds
# `exposure_time_absolute` and `white_balance_temperature` at `flags=inactive` until it is
# turned off. `auto_exposure` is a V4L2 menu whose automatic entry is 3, not a boolean.
AUTO_EXPOSURE_APERTURE_PRIORITY = 3
ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON = 1
ARDUCAM_EXPOSURE_TIME_ABSOLUTE = 60
ARDUCAM_GAIN = 200
ARDUCAM_WHITE_BALANCE_TEMPERATURE_K = 4000

# Where an unconfigured B0495 actually sits: both driving controls pinned at their maximum,
# which clips every frame to white. This is the state a camera opened with no declaration is
# in, and it reads as "the detector is bad" rather than as a camera fault.
ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE = 660
ARDUCAM_STOCK_GAIN = 1600
ARDUCAM_EXPOSURE_TIME_MINIMUM = 5
ARDUCAM_GAIN_MINIMUM = 168

# Not measured on this model — the white-balance entry carries the inactive-flag rule, while
# the silent-clamp rule rides on exposure, whose bounds above are measured.
ARDUCAM_WHITE_BALANCE_TEMPERATURE_MINIMUM = 2800
ARDUCAM_WHITE_BALANCE_TEMPERATURE_MAXIMUM = 6500

# The module streams YUYV only; it offers no MJPEG (`06` §2.9 bandwidth then scales with
# resolution×fps directly, since nothing is compressed).
ARDUCAM_PIXEL_FORMAT = "YUYV"

# A FOURCC packs four ASCII bytes low-to-high into one 32-bit word.
FOURCC_CHARACTER_BITS = 8
FOURCC_CHARACTER_COUNT = 4
