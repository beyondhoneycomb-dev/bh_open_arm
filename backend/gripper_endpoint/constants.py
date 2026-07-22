"""Domain constants for the gripper (J8) endpoint capture and sign-mirror schema.

The single source of truth for the DM4310 velocity ceiling is the CAN register
table (`backend.can.rid.motor_limits`); this module derives the gripper POS_FORCE
speed cap from it rather than restating 30 rad/s, so a change to the register table
carries into the cap without a second edit (`03` FR-MOT-046/049, `16` D-5).
"""

from __future__ import annotations

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType

SIDE_LEFT = "left"
SIDE_RIGHT = "right"
SIDES = (SIDE_LEFT, SIDE_RIGHT)

# The gripper is the eighth actuator on each follower arm, a DM4310 (`03` FR-MOT-046).
GRIPPER_MOTOR_TYPE = MotorType.DM4310

# POS_FORCE speed cap ceiling, rad/s. The upstream `gripper_posforce_limits[0]=50.0`
# literal is a DM3507 figure and is physically unreachable on a DM4310, so a requested
# gripper speed is clamped at the DM4310 register V_MAX (`03` FR-MOT-049).
GRIPPER_SPEED_CAP_RAD_S = MOTOR_LIMIT_PARAMS[GRIPPER_MOTOR_TYPE].v_max

# The normalized open/close command domain of the norm[0,1] linear map (FR-MAN-016).
NORM_MIN = 0.0
NORM_MAX = 1.0

# The per-unit force domain. Grip force is exposed per-unit only; a value outside this
# range is a physical-force-unit intrusion and is refused, since the per-unit-to-force
# conversion is undetermined and no load cell is used (FR-MAN-016, FR-SAF-024b).
TORQUE_PU_MIN = 0.0
TORQUE_PU_MAX = 1.0

# Float tolerance for the sign-mirror equality `left == (-hi_right, -lo_right)`. The
# relation is exact by construction; this only absorbs JSON round-trip float noise.
MIRROR_TOLERANCE_RAD = 1e-9

# The smallest endpoint separation that still defines a norm map. Below it the linear
# map divides by ~0, so the capture is rejected rather than yielding infinities.
MIN_ENDPOINT_SEPARATION_RAD = 1e-6

# The persisted-record schema generation and its on-disk file suffix. The suffix is
# distinct from the calibration file's `.oa_cal.json` so the two persistence
# mechanisms never read each other's bytes.
SCHEMA_VERSION = 1
RECORD_SUFFIX = ".oa_gripper.json"
