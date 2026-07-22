"""Temperature-fault caps and gripper exception handling (WP-2C-11).

Three exception paths the collision-detection band needs but that are not residual
detection:

* `temperature` — per-motor driver/coil over-temperature grading with the FR-SAF-026
  fault caps (driver 115 °C, coil 95 °C) enforced below the motor's own self-protection,
  so a fault holds the arm before the motor self-disables (= a fall). Its input is the
  two temperature bytes `feedback` decodes from the DM frame (D[6] = T_MOS driver,
  D[7] = T_Rotor coil).
* `residual_policy` — the FR-SAF-024 default: the gripper is excluded from residual
  (GMO) collision detection, with the reason reused from WP-2B-01 (`GRIPPER_MODEL_REASON`:
  no finger dynamics model + grasp reaction = constant torque offset), NOT "no torque
  observation" — the torque is observed.
* `grasp` / `labels` — grasp-force monitoring by the absolute value of gripper.torque in
  the per-unit domain [0, 1] only (FR-SAF-024b); no string a user sees carries a physical
  force unit, since the per-unit-to-force constant is undetermined.
"""

from __future__ import annotations

from backend.temp_gripper.constants import (
    COIL_TEMP_FAULT_CAP_C,
    DRIVE_TEMP_FAULT_CAP_C,
    GRASP_CONTACT_THRESHOLD_PU_DEFAULT,
    GRASP_FORCE_CAP_PU_DEFAULT,
    GRIPPER_JOINT_INDEX,
    GRIPPER_TORQUE_IS_OBSERVED,
    MOTOR_COUNT_PER_ARM,
)
from backend.temp_gripper.errors import TempGripperConfigError
from backend.temp_gripper.feedback import MotorThermal, decode_motor_thermal
from backend.temp_gripper.grasp import GraspForceMonitor, GraspState, GraspVerdict
from backend.temp_gripper.labels import (
    GRASP_FORCE_VALUE_LABEL,
    USER_FACING_GRASP_LABELS,
)
from backend.temp_gripper.residual_policy import (
    GRIPPER_RESIDUAL_DISABLED_REASON,
    gripper_motor_indices,
    gripper_torque_is_observed,
    mask_gripper_residual,
    residual_detection_enabled_for,
)
from backend.temp_gripper.temperature import (
    ChannelReading,
    TemperatureMonitor,
    TemperatureThresholds,
    TemperatureVerdict,
    TempSeverity,
    default_thresholds,
)

__all__ = [
    "COIL_TEMP_FAULT_CAP_C",
    "DRIVE_TEMP_FAULT_CAP_C",
    "GRASP_CONTACT_THRESHOLD_PU_DEFAULT",
    "GRASP_FORCE_CAP_PU_DEFAULT",
    "GRASP_FORCE_VALUE_LABEL",
    "GRIPPER_JOINT_INDEX",
    "GRIPPER_RESIDUAL_DISABLED_REASON",
    "GRIPPER_TORQUE_IS_OBSERVED",
    "MOTOR_COUNT_PER_ARM",
    "USER_FACING_GRASP_LABELS",
    "ChannelReading",
    "GraspForceMonitor",
    "GraspState",
    "GraspVerdict",
    "MotorThermal",
    "TempGripperConfigError",
    "TempSeverity",
    "TemperatureMonitor",
    "TemperatureThresholds",
    "TemperatureVerdict",
    "decode_motor_thermal",
    "default_thresholds",
    "gripper_motor_indices",
    "gripper_torque_is_observed",
    "mask_gripper_residual",
    "residual_detection_enabled_for",
]
