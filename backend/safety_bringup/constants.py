"""Named constants for the extended safety bring-up (WP-1-06).

Every value here is a spec-given identifier, an asset-derived physical quantity, or a
provenance label — never a measured pass line. The velocity canon and the collision
threshold floor are *derived by arithmetic* from committed sources (the register limit
table, the URDF, the motor datasheet), because `03` §5.6.0 and `12` FR-SAF-019 make the
point that a safety limit is derived from physics, never measured from the hardware whose
limit it is: the register V_MAX a motor reports is not allowed to be the source of its own
ceiling.

The torque-LSB floor is computed here from `MOTOR_LIMIT_PARAMS` (the packet T_MAX table)
rather than re-typed, so a change to the canonical table moves the floor with it; the
spec-quoted figures (DM8009 0.264 / DM4340 0.137 / DM4310 0.049 Nm) are asserted against
the derivation in the tests, not re-declared as independent literals.
"""

from __future__ import annotations

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType

# The gates this WP produces or consumes (`03` gate table, `02a` §8). PG-VEL-001 is the
# derived-velocity gate this WP owns; the others are preconditions it reads. The
# provisional-f_max lineage (PG-RT-001a/b) is WP-1-04's, so its re-derivation trigger is
# imported at its point of use (see band.py), not restated here.
PG_VEL_001 = "PG-VEL-001"
PG_SAFE_001 = "PG-SAFE-001"
PG_VMAX_001 = "PG-VMAX-001"
PG_FRIC_001 = "PG-FRIC-001"

GATE_STATE_PASS = "PASS"
GATE_STATE_FAIL_BLOCKING = "FAIL_BLOCKING"

# The seven actuated arm joints, in order, and the motor family driving each (`03` §2.1
# motor table / MJCF joint classes). J1/J2 are the DM8009 shoulder, J3/J4 the DM4340
# elbow, J5-J7 the DM4310 wrist. The gripper (finger) joint is not an arm joint and is
# clamped separately (`16` D-5), so it is excluded from this arm-limit vector.
ARM_JOINT_COUNT = 7
ARM_JOINT_MOTORS: tuple[MotorType, ...] = (
    MotorType.DM8009,
    MotorType.DM8009,
    MotorType.DM4340,
    MotorType.DM4340,
    MotorType.DM4310,
    MotorType.DM4310,
    MotorType.DM4310,
)

# A signed 12-bit torque field spans -T_MAX..+T_MAX across (2^12 - 1) levels, so one LSB
# is 2*T_MAX/4095 Nm (`03` §2.3 packet encoding, `04` §2.7 torque resolution). The floor
# a per-joint collision threshold may not be set below is ten LSBs (`12` FR-SAF-019).
TORQUE_ENCODING_LEVELS = (1 << 12) - 1
COLLISION_THRESHOLD_FLOOR_LSB_MULTIPLE = 10


def torque_lsb_nm(motor: MotorType) -> float:
    """Return the torque-field LSB for a motor type, in Nm (`03` §2.3, `04` §2.7).

    Args:
        motor: The motor family whose packet T_MAX sets the encoding span.

    Returns:
        (float) Newton-metres per least-significant bit of the 12-bit torque field.
    """
    t_max = MOTOR_LIMIT_PARAMS[motor].t_max
    return 2.0 * t_max / TORQUE_ENCODING_LEVELS


def collision_threshold_floor_nm(motor: MotorType) -> float:
    """Return the per-joint collision-threshold floor for a motor type (`12` FR-SAF-019).

    The floor is ten torque-field LSBs: a threshold set below it cannot be distinguished
    from quantisation noise, so it is physics-owned and a user cannot set below it.

    Args:
        motor: The motor family at the joint.

    Returns:
        (float) The lowest admissible collision torque threshold, Nm.
    """
    return torque_lsb_nm(motor) * COLLISION_THRESHOLD_FLOOR_LSB_MULTIPLE


# The URDF per-joint effort limit, Nm (`03` §2.1 / joint_limits.yaml — effort equals peak
# torque exactly: 40/40/27/27/7/7/7). The default collision threshold is +-10% of it
# (`12` FR-SAF-020), a literature-rule starting point, NOT an OpenArm-measured value.
URDF_EFFORT_LIMIT_NM: tuple[float, ...] = (40.0, 40.0, 27.0, 27.0, 7.0, 7.0, 7.0)
DEFAULT_COLLISION_THRESHOLD_FRACTION = 0.10

# The mandatory provenance label on the default collision threshold (`12` FR-SAF-020,
# acceptance ⑤). Its presence is a static-checkable fact; its absence promotes a
# theoretical figure to a measured one, which is the confusion the label exists to stop.
THEORETICAL_THRESHOLD_LABEL = (
    "theoretical starting point derived from a literature rule "
    "(+-10% of URDF effort); NOT an OpenArm-measured value"
)

# The URDF per-joint velocity limit, rad/s (`03` §2.1 line 351 / joint_limits.yaml). This
# is the physical canon for J3/J4 where it undercuts the register V_MAX (`03` trap 2).
URDF_VELOCITY_LIMIT_RAD_S: tuple[float, ...] = (
    16.755,
    16.755,
    5.4454,
    5.4454,
    20.944,
    20.944,
    20.944,
)

# The `12` §2.5 velocity cap, rad/s. Upstream this is active only behind `--limit-velocity`
# and the default is NO limit (`16` §11 trap 7); WP-1-06 flips that default to active
# (acceptance ⑩). Overlaid onto the physical derivation as the conservatising step
# (`03` §5.6.0 ②), it is the tightest source for every joint.
VELOCITY_CAP_RAD_S: tuple[float, ...] = (1.57, 1.57, 3.14, 3.14, 12.6, 12.6, 12.6)

# Catalogue max no-load speed, rad/s, keyed by motor type. Only DM4340 is quoted in the
# corpus (52 rpm ~= 5.45 rad/s, `03` trap 2); the DM8009/DM4310 catalogue figures are not
# in the committed sources, so they are absent rather than invented — a motor with no
# catalogue entry simply contributes no candidate to its joint's three-way minimum, and
# the derivation report says so instead of guessing.
CATALOGUE_NO_LOAD_SPEED_RAD_S: dict[MotorType, float] = {
    MotorType.DM4340: 5.45,
}

# The gripper (DM4310) POS_FORCE speed clamp ceiling, rad/s (`16` D-5, `03` FR-MOT-049):
# the upstream 50 rad/s is a DM3507 figure and is physically unreachable, so gripper speed
# is clamped at the DM4310 register V_MAX. Recorded for the derivation report; the gripper
# is not one of the seven arm joints this WP's arm-limit vector covers.
GRIPPER_SPEED_CLAMP_RAD_S = MOTOR_LIMIT_PARAMS[MotorType.DM4310].v_max

# The default collision margin, metres (`12` FR-SAF-011). A request below it warns; a
# request of exactly zero warns and additionally requires an explicit confirmation.
COLLISION_MARGIN_DEFAULT_M = 0.02

# The MJCF body that carries joint 7 is the wrist-distal link ("link7" in URDF terms —
# `ee_base_link` in the vendored MJCF, `09` v2 asset). The collision check finds the body
# owning a `*joint7` and asserts it declares a collision-class geom (`12` FR-SAF-010).
MJCF_JOINT7_SUFFIX = "joint7"
MJCF_COLLISION_CLASS = "collision"

# Symbols of the deprecated octomap environment-collision pipeline (`12` FR-SAF-012). The
# canonical camera config has zero depth streams, so the MoveIt sensors_3d input never
# exists; environment collision is MJCF cell geom instead. The static scan requires zero
# references to these in the code tree (acceptance ⑦).
OCTOMAP_DEPRECATED_SYMBOLS: tuple[str, ...] = (
    "octomap",
    "OcTree",
    "sensors_3d",
    "PointCloudOctomapUpdater",
)

# The teleop QP-IK path has NO pre-collision check, and `12` FR-SAF-015 requires the UI to
# say so rather than let an operator assume a guard that is not there. This is the exact
# string the presence check (acceptance ⑧) looks for.
TELEOP_NO_PRECHECK_UI_STRING = "Teleop (QP IK): NO pre-collision check on this path"

# CAN-FD frame budget bands (`15` §2.1 / `01` NFR-SYS-002). Pattern A reads 16 frames per
# cycle and admits the 1 kHz detection loop (`12` NFR-SAF-001); pattern B reads 32 and
# caps the loop at the CAN-FD ceiling of 625 Hz with a degraded flag and an effective-
# latency display (acceptance ⑪).
DETECTION_LOOP_TARGET_HZ = 1000.0
DETECTION_LOOP_PATTERN_B_CEILING_HZ = 625.0
FRAMES_PER_CYCLE_PATTERN_A = 16
FRAMES_PER_CYCLE_PATTERN_B = 32

# Environment variable pointing the deferred-sweep re-verification hook at a directory of
# real single-joint sweep captures (`02a` §4.1). Until it is set, the command-following
# sweep acceptances (⑨-a/⑨-b) skip with a reason and are never asserted green.
FIXTURE_ENV_VAR = "OPENARM_SAFETY_BRINGUP_REAL_FIXTURE"
