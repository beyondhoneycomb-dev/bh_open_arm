"""Named reference values for the tolerant camera-connect layer (`06` §2.12/§4).

Each value here is a domain quantity the tolerant-connect path needs in exactly one
place. Two carry a deliberate caveat, mirroring `backend/camera/constants.py`: the
USB2 budget is a *reference* signalling rate, not a confirmed acceptance target —
`PG-CAM-001` fixes the effective ceiling only after real cameras are observed
(`02a` WP-0B-08 ⑨). The connect functions take the budget as a parameter and default
to this; a block rendered against it is the block *logic* proven, never a nailed cap.
"""

from __future__ import annotations

# How many frame indices the connect probe looks back over to decide a camera is
# live. A healthy camera yields a frame immediately, so a shallow window is enough
# to tolerate a single startup drop without waiting on a long stream. This is a
# grab-window depth, not a timeout: the synthetic fixture's `read_latest(up_to)`
# walks 0..up_to and returns the freshest live frame (`contracts/fixtures`).
DEFAULT_PROBE_DEPTH = 2

# USB 2.0 high-speed nominal signalling rate in Mbps (USB-IF, a published bus fact,
# not a measurement). It is the default budget the FR-CAM-003 profile block comes in
# under when a camera negotiates a USB2 fallback link. The *effective* USB2 ceiling
# is decided at `PG-CAM-001` like the USB3 reference in `backend/camera/constants.py`,
# so callers override this; a green here never means a profile cleared a frozen line.
USB2_NOMINAL_MBPS = 480

# The directory of real captured output the deferred re-verification hook consumes
# (`02a` §4.1). Distinct from WP-0B-08's `OPENARM_CAMERA_REAL_FIXTURE` so a rig can
# point the two harnesses at different corpora; the descriptor/binding file shapes
# are shared and loaded through `backend.camera.reverify`.
REAL_FIXTURE_ENV_VAR = "OPENARM_SENSING_REAL_FIXTURE"

DESCRIPTORS_FILENAME = "descriptors.json"
BINDING_FILENAME = "binding.json"
LIVENESS_FILENAME = "liveness.json"
EXPECTED_FILENAME = "expected.json"
