"""Domain constants for the temperature-fault caps, the gripper residual exclusion,
and the per-unit grasp-force thresholds (WP-2C-11).

The joint layout (`ARM_JOINT_COUNT`, the gripper as the eighth per-arm motor) is
inherited from WP-2B-01 (`backend.dynamics.constants`) rather than restated, so the
arm/gripper split has one owner. The per-unit force domain is inherited from WP-2A-08
(`backend.gripper_endpoint.constants`) for the same reason.
"""

from __future__ import annotations

from backend.dynamics.constants import ARM_JOINT_COUNT

# --- DM feedback frame temperature bytes (spec 03 §2.7 feedback frame) ---
# The Damiao MIT feedback frame packs two 1-byte temperatures in its last two bytes:
# D[6] = T_MOS (driver MOSFET temperature, °C), D[7] = T_Rotor (motor coil
# temperature, °C), both unsigned integer °C (spec 03 §2.7, FR-MOT-040). D[0] carries
# the ERR nibble decoded elsewhere (backend.actuation.errdecode); this package reads
# only the two temperature bytes.
DRIVE_TEMP_BYTE_INDEX = 6
COIL_TEMP_BYTE_INDEX = 7
FEEDBACK_FRAME_MIN_LEN = 8
TEMP_BYTE_MIN = 0
TEMP_BYTE_MAX = 255

# Channel names for a per-motor thermal reading — the two feedback temperatures.
DRIVE_CHANNEL = "drive"
COIL_CHANNEL = "coil"

# --- Temperature fault caps (FR-SAF-026) ---
# The fault threshold is capped below the motor's own self-protection so the arm is
# held under command before the motor drops its own enable — a self-disable at
# temperature is the brakeless fall this exists to pre-empt. The Damiao driver
# self-protects the MOSFET at a fixed 120 °C and the coil at a recommended ≤100 °C
# (spec 12 §2.2); FR-SAF-026 sets our fault cap under both. A configured fault above
# its cap is refused, not clamped.
DRIVE_TEMP_FAULT_CAP_C = 115.0
COIL_TEMP_FAULT_CAP_C = 95.0

# Conservative two-stage warn defaults (FR-MOT-040 warn/fault two-stage). The exact
# DM-rated warning temperatures are unconfirmed (spec 04 open item Q10), so these are
# operator-tunable margins below the fault caps, never a datasheet-asserted figure.
DRIVE_TEMP_WARN_DEFAULT_C = 100.0
COIL_TEMP_WARN_DEFAULT_C = 80.0

# --- Gripper residual-detection exclusion (FR-SAF-024) ---
# The gripper is the eighth motor of a follower arm (indices 0..6 are the arm joints,
# index 7 the gripper; spec 03 FR-MOT-001 motor_config), so one arm reports
# ARM_JOINT_COUNT + 1 motors.
GRIPPER_COUNT_PER_ARM = 1
MOTOR_COUNT_PER_ARM = ARM_JOINT_COUNT + GRIPPER_COUNT_PER_ARM
GRIPPER_JOINT_INDEX = ARM_JOINT_COUNT

# The gripper's torque IS observed: the LeRobot follower's sync_read_all_states()
# fills gripper.torque in one CAN refresh cycle (spec 12 FR-SAF-024,
# openarm_follower.py:239-246). Recording this keeps the residual-exclusion reason
# honest — the exclusion is the missing dynamics model and the grasp-reaction offset,
# NOT absent torque observation.
GRIPPER_TORQUE_IS_OBSERVED = True

# --- Per-unit grasp-force thresholds (FR-SAF-024b) ---
# Grasp force is monitored by the absolute value of gripper.torque in the per-unit
# domain [0, 1] only. The per-unit-to-force constant is undetermined (spec 12 §5-Q14)
# and no load cell is used, so no physical force unit is asserted or displayed. These
# defaults are per-unit configuration, not a measured physical force.
GRASP_CONTACT_THRESHOLD_PU_DEFAULT = 0.05
GRASP_FORCE_CAP_PU_DEFAULT = 0.8
