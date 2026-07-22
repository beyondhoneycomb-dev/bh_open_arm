"""Named values for the camera calibration subsystem (WP-3B-13).

Every literal that carries a calibration decision lives here so the solver, the
store, and the persistence layer read one source. `06` FR-CAM-026 fixes the
five hand-eye method names and their order; FR-CAM-030 leaves the recommended
sample-pose count unmeasured, which this module represents as an explicit
`None` rather than a fabricated number.
"""

from __future__ import annotations

# Translations throughout the subsystem are SI metres (the unit the arm pose and
# camera-extrinsic streams carry). Deviations are surfaced in millimetres because
# that is the scale a hand-eye disagreement is read at (`06` FR-CAM-026), so the
# conversion factor is named once here.
MM_PER_METRE = 1000.0

# The five hand-eye solvers `06` FR-CAM-026 mandates be computed *simultaneously*,
# in the canonical presentation order. The order is contract: a UI that renders
# the deviation table reads methods in this sequence, and the YAML record stores
# them under these exact keys. `cv2.CALIB_HAND_EYE_*` flags are resolved from these
# names in `handeye`, so the numeric flag never leaks into a stored record.
HAND_EYE_METHOD_NAMES = ("TSAI", "PARK", "HORAUD", "ANDREFF", "DANIILIDIS")

# The mathematical floor for a hand-eye solve: `cv2.calibrateHandEye` needs at
# least two relative motions, so three distinct poses. This is the solver's hard
# minimum, not the *recommended* count — that is `RECOMMENDED_SAMPLE_POSES_DEFAULT`
# and is unmeasured.
MIN_POSES_FOR_HAND_EYE = 3

# `cv2.calibrateCamera` needs several board views to constrain focal length,
# principal point and distortion together; below this the solve is under-determined.
MIN_VIEWS_FOR_INTRINSIC = 3

# The distortion model persisted and reported: OpenCV's five-term
# (k1, k2, p1, p2, k3), the plumb-bob model `cv2.calibrateCamera` returns by
# default. Named so the record schema and the reverify hook agree on the width.
DISTORTION_COEFFICIENT_COUNT = 5

# `06` FR-CAM-030: the recommended hand-eye sample-pose count is exposed as a
# setting whose default is *measured*, not chosen. Until that measurement exists
# the default is absent — `None`, never a guessed integer. A caller that wants a
# working default must supply one; the subsystem will not invent a spec value.
RECOMMENDED_SAMPLE_POSES_DEFAULT: int | None = None

# The on-disk calibration record extension. One record per camera slot, keyed by
# the `CTR-PRIM@v1` slot key (`06` FR-CAM-027).
CALIBRATION_FILE_SUFFIX = ".oa_calibration.yaml"
