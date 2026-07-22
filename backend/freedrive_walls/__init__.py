"""WP-2D-04 — Freedrive virtual-wall repulsion torque and the detection switch.

Two products behind `04` FR-MAN-036/037 and `02b` §4.2 WP-2D-04:

  * The **joint-limit virtual wall** (`repulsion`) — within 5 deg of a limit, a repulsion
    torque added to the MIT `tau` pushes the joint back toward the interior, capped within the
    URDF effort (a cap over effort is refused, not clamped: `RepulsionEffortExceededError`).
    In torque mode LeRobot's position clip is void (`torque_mode`), so this torque is what
    enforces the limit.

  * The **detection switch** (`detection`) — Freedrive suppresses the residual (GMO) trip,
    because a hand-guide force is itself an external residual, but keeps every hardware-fault
    and limit-violation trip live. Switching one of those off is FAIL_BLOCKING
    (`DetectionRetainedError`).

Reused, not rebuilt: the soft limits are `sim.ik.limits` (LeRobot's own); the effort ceiling
is `backend.safety_bringup`'s canonical URDF table; the residual comparison is `backend.gmo`;
the motor-fault and comm-loss trips are `backend.commloss`; the over-temperature trip is
`backend.temp_gripper`; and the Cartesian keep-out (`cartesian_walls`) is the WP-2C-07
`sim.walls` check by identity, never a second wall geom.
"""

from __future__ import annotations

from backend.freedrive_walls.constants import (
    DEFAULT_REPULSION_EFFORT_FRACTION,
    MAX_REPULSION_EFFORT_FRACTION,
    NEAR_LIMIT_BAND_RAD,
)
from backend.freedrive_walls.detection import (
    FREEDRIVE_SUPPRESSIBLE_DETECTORS,
    HARDWARE_FAULT_DETECTORS,
    MANDATORY_RETAINED_DETECTORS,
    DetectorKind,
    FreedriveDetectionSuite,
    FreedriveDetectionVerdict,
    FreedriveResidualPolicy,
    FreedriveResidualVerdict,
    assert_freedrive_detection_retained,
    limit_violation,
)
from backend.freedrive_walls.errors import (
    DetectionRetainedError,
    FreedriveConfigError,
    FreedriveWallError,
    RepulsionEffortExceededError,
)
from backend.freedrive_walls.repulsion import (
    JointLimitRepulsion,
    JointWall,
    build_arm_repulsion,
)
from backend.freedrive_walls.torque_mode import (
    POSITION_CLIP_VOID_IN_TORQUE_MODE_NOTE,
    modeled_lerobot_position_clip,
    position_clip_is_void,
)

__all__ = [
    "DEFAULT_REPULSION_EFFORT_FRACTION",
    "FREEDRIVE_SUPPRESSIBLE_DETECTORS",
    "HARDWARE_FAULT_DETECTORS",
    "MANDATORY_RETAINED_DETECTORS",
    "MAX_REPULSION_EFFORT_FRACTION",
    "NEAR_LIMIT_BAND_RAD",
    "POSITION_CLIP_VOID_IN_TORQUE_MODE_NOTE",
    "DetectionRetainedError",
    "DetectorKind",
    "FreedriveConfigError",
    "FreedriveDetectionSuite",
    "FreedriveDetectionVerdict",
    "FreedriveResidualPolicy",
    "FreedriveResidualVerdict",
    "FreedriveWallError",
    "JointLimitRepulsion",
    "JointWall",
    "RepulsionEffortExceededError",
    "assert_freedrive_detection_retained",
    "build_arm_repulsion",
    "limit_violation",
    "modeled_lerobot_position_clip",
    "position_clip_is_void",
]
