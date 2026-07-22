"""Named reference values for the teleop clutch / scale / smoother / align layer.

Every value here is a `05` §3 parameter-table quantity (the mapping, clutch, align and
filter rows) with a default and an operator-adjustable range. They live in one place so
the components below take them as constructor defaults and a GUI (`WP-3B-15`, S-05) can
offer the same ranges without re-deriving them. None of these is a hardware measurement
gated behind a `PG-*`: they are upstream-observed control-tuning values (`dora-openarm`,
XRoboToolkit) that the plan froze as defaults (`05` §3.5/§3.11, `FR-TEL-029`..`040`/`083`).
"""

from __future__ import annotations

# Clutch (deadman) grip threshold — `05` §3 clutch row, `FR-TEL-030`. The squeeze
# analog must be at or above this to engage following; below it the follower holds.
# Upstream XRoboToolkit compares `xr_grip_val > 0.9`; the spec states "at or above"
# (>=), so the gate uses `>=` and the two levels partition the axis (engaged | released).
DEADMAN_THRESHOLD_DEFAULT = 0.9
DEADMAN_THRESHOLD_MIN = 0.5
DEADMAN_THRESHOLD_MAX = 0.99

# Position scale — `05` §3 mapping row, `FR-TEL-033`. EE target = ref_EE + (controller
# delta) x this. Upstream OpenArm paths have no scale (1:1 absolute); XRoboToolkit's
# `DEFAULT_SCALE_FACTOR = 0.8` is the adopted default.
POSITION_SCALE_DEFAULT = 0.8
POSITION_SCALE_MIN = 0.1
POSITION_SCALE_MAX = 2.0

# Rotation scale — `05` §3 mapping row, `FR-TEL-029`. Independent of position scale because
# joint6 is only ±0.7854 rad (±45°): a 1:1 attitude mapping is always at the limit, so
# the operator narrows rotation without touching translation.
ROTATION_SCALE_DEFAULT = 1.0
ROTATION_SCALE_MIN = 0.0
ROTATION_SCALE_MAX = 1.0

# One Euro pose-smoother parameters — `05` §3 filter row, `FR-TEL-039`. `smoothing.py`
# in-use values, identical on the UDP and WebXR paths. `min_cutoff` sets the floor
# cutoff frequency (Hz), `beta` the speed coefficient that raises the cutoff with
# motion, `d_cutoff` the cutoff of the derivative (speed) filter.
MIN_CUTOFF_DEFAULT = 2.0
MIN_CUTOFF_MIN = 0.1
MIN_CUTOFF_MAX = 20.0

BETA_DEFAULT = 0.04
BETA_MIN = 0.0
BETA_MAX = 1.0

D_CUTOFF_DEFAULT = 1.5
D_CUTOFF_MIN = 0.1
D_CUTOFF_MAX = 10.0

# Alignment ramp rate — `05` §3 align row, `FR-TEL-083`. A rate in rad/second, NOT a
# per-frame constant: the per-frame step is derived as `align_rate_rad_s / fps`, so the
# achieved rate stays 0.5 rad/s at any loop rate. The 0.5 default is the upstream dora
# `0.001 rad/event × 500 Hz`; encoding that 0.001 rad/event directly would collapse to
# 0.06 rad/s at 60 Hz (`AlignRamp` and its test exist to keep that from happening).
ALIGN_RATE_RAD_S_DEFAULT = 0.5
ALIGN_RATE_RAD_S_MIN = 0.1
ALIGN_RATE_RAD_S_MAX = 2.0

# Alignment convergence band — `05` §3 align row. ALIGNING is complete once every joint is
# within this many radians of the target; the state machine (`WP-3B-10`, S3→S4) reads
# it. Held here because the ramp and the convergence test share one threshold.
ALIGN_THRESHOLD_RAD_DEFAULT = 0.1
ALIGN_THRESHOLD_RAD_MIN = 0.02
ALIGN_THRESHOLD_RAD_MAX = 0.5

# Default teleop loop rate (Hz) — `05` §3 loop row. The per-frame align step and the
# smoother's default-dt fallback are derived against this when a caller supplies none.
LOOP_FPS_DEFAULT = 60

# Nanoseconds per second. The VR sample carries its receive instant as monotonic
# nanoseconds (`CTR-TEL@v1` TeleopSample); the smoother differences timestamps in
# seconds, so the conditioner divides by this rather than a bare 1e9 literal.
NANOS_PER_SECOND = 1_000_000_000
