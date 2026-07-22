"""Named reference values for the VR UDP pose source (`05` §2.7/§2.8, WP-3B-07).

Two kinds of value live here: the wire protocol the Quest APK speaks (port,
buffer, delimiter, the fixed JSON keyset) and the coordinate-transform constants
that map an XR controller pose into the MuJoCo world frame. The transform matrix,
its quaternion twin and the offset are confirmed across five independent
codebases (`05` §2.8), so they are stated once here and consumed by `transform`.
"""

from __future__ import annotations

from backend.teleop.vr_udp.geometry import Mat3, Quat, Vec3

# --- UDP wire (Quest APK path A, `05` §2.7; `quest_receiver`/`udp_receiver`) -------

# The datagram socket the Quest APK streams plaintext JSON to. Unprivileged, so a
# test binds it (or an ephemeral port) on loopback without elevation.
UDP_PORT_DEFAULT = 5006

# Bind on all interfaces by default: the headset is a separate device on the LAN,
# not loopback. Tests override host/port to bind loopback on an ephemeral port.
UDP_HOST_DEFAULT = "0.0.0.0"

# Receive buffer, matching the upstream `udp_receiver.py:26` 4096-byte read. One
# datagram carries one newline-terminated frame; a larger frame is a protocol error.
RECV_BUFFER_BYTES = 4096

# Frames are newline-terminated UTF-8 JSON (`05` §2.7). A datagram may in principle
# carry more than one frame, so the receiver splits on this delimiter.
FRAME_DELIMITER = b"\n"
TEXT_ENCODING = "utf-8"

# Seconds the blocking receive waits before checking the stop flag. Bounds shutdown
# latency without busy-looping; it is not a heartbeat timeout (that is WP-3B-10).
RECV_POLL_TIMEOUT_S = 0.2

# --- JSON keyset (`FR-TEL-014`; the frozen wire keys) ------------------------------

# The source clock stamped by the headset — the CLIENT clock, an age input only,
# never the expiry authority (`CTR-TEL@v1` `SOURCE_TS_ROLE`).
KEY_SOURCE_TS = "t"

# Per-arm controller position (`lc`/`rc`) and orientation quaternion (`lt`/`rt`,
# scalar-last on the wire). The synthetic stream carries orientation in `lt`/`rt`
# (`contracts/fixtures/vr_pose_stream.py`); a real headset's trigger-vs-orientation
# semantics for these keys are unconfirmed (`05` §5 U-12) and are the deferred item.
KEY_LEFT_POSITION = "lc"
KEY_RIGHT_POSITION = "rc"
KEY_LEFT_QUATERNION = "lt"
KEY_RIGHT_QUATERNION = "rt"

# Optional NECK reference pose subtracted before rotation. Absent on the synthetic
# stream, so the subtraction is identity here; its exact real-headset semantics are
# unconfirmed (`05` §5 U-12), deferred to real-hardware re-verification.
KEY_REFERENCE_POSE = "rf"

# Per-arm analog grip in [0, 1] (the clutch input). Carried through untouched: the
# grip->clutch threshold is WP-3B-09, the trigger->gripper-angle map is WP-2A-08.
KEY_LEFT_GRIP = "lg"
KEY_RIGHT_GRIP = "rg"

# Optional thumbstick axes; absent on the synthetic stream, tolerated when present.
KEY_LEFT_STICK_X = "lsx"
KEY_LEFT_STICK_Y = "lsy"
KEY_RIGHT_STICK_X = "rsx"
KEY_RIGHT_STICK_Y = "rsy"

# Face buttons.
KEY_BUTTON_A = "a"
KEY_BUTTON_B = "b"
KEY_BUTTON_X = "x"
KEY_BUTTON_Y = "y"

# Three-level validity wire fields: overall, left, right (`05` §2.7; 0/1/2).
KEY_VALIDITY = "v"
KEY_LEFT_VALIDITY = "vl"
KEY_RIGHT_VALIDITY = "vr"

# The two arms, in `CTR-PRIM@v1` order.
LEFT = "left"
RIGHT = "right"
ARM_SIDES = (LEFT, RIGHT)

# Per-arm wire-key lookup, so the parser reads a side without branching on strings.
ARM_POSITION_KEY = {LEFT: KEY_LEFT_POSITION, RIGHT: KEY_RIGHT_POSITION}
ARM_QUATERNION_KEY = {LEFT: KEY_LEFT_QUATERNION, RIGHT: KEY_RIGHT_QUATERNION}
ARM_GRIP_KEY = {LEFT: KEY_LEFT_GRIP, RIGHT: KEY_RIGHT_GRIP}
ARM_VALIDITY_KEY = {LEFT: KEY_LEFT_VALIDITY, RIGHT: KEY_RIGHT_VALIDITY}
BUTTON_KEYS = (KEY_BUTTON_A, KEY_BUTTON_B, KEY_BUTTON_X, KEY_BUTTON_Y)

# --- Coordinate transform (`05` §2.8; confirmed in five codebases) -----------------

# XR (X=right, Y=up, Z=back) -> robot world (X=front, Y=left, Z=up). det = +1.
# Checksum: x_robot = -z_xr, y_robot = -x_xr, z_robot = +y_xr.
R_ROBOT: Mat3 = (
    (0.0, 0.0, -1.0),
    (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
)

# The same rotation as `R_ROBOT`, as a scalar-first quaternion, so the orientation
# is rotated without a matrix<->quaternion round-trip per frame. Derived by hand
# from `R_ROBOT` (trace 0: w = 1/2; x = 1/2; y = -1/2; z = -1/2); a test reconstructs
# `R_ROBOT` from it and fails if the two ever drift apart.
Q_ROBOT: Quat = (0.5, 0.5, -0.5, -0.5)

# FRAME_OFFSET_NECK / _FRAME_OFFSET_CELL — the same translation on both VR paths.
FRAME_OFFSET: Vec3 = (0.1, 0.0, 1.2)

# This source outputs poses already in the robot world frame: `R_ROBOT` is applied
# here and exactly once. Downstream declares `frame_applied` and must not re-apply
# it: a second multiply flips the axes (`05` §2.8, no double transform).
FRAME_APPLIED = True

# The output pose is `float32[7] = [px, py, pz, qw, qx, qy, qz]`, scalar-first
# (`FR-TEL-025`).
POSE_DIMENSION = 7
