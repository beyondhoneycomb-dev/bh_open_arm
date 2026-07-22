"""User-facing strings for the grasp-force surface — per-unit only, no force unit.

Grasp force is exposed as the per-unit |gripper.torque| magnitude in [0, 1]. The
per-unit-to-force constant is undetermined (spec 12 §5-Q14) and no load cell is used,
so no string a user sees carries a physical force unit (FR-SAF-024b). The WP-2C-11
static check scans this surface — and the whole package's string literals — to confirm
no force-unit label reaches the grasp-force UI (acceptance ④, zero force-unit labels).
The forbidden-token list lives in the static check, not here, so this package carries
no such token in any string literal of its own.
"""

from __future__ import annotations

GRASP_FORCE_VALUE_LABEL = "grip force (per-unit, 0-1)"
GRASP_STATE_RELEASED_LABEL = "released"
GRASP_STATE_GRASPING_LABEL = "grasping"
GRASP_STATE_OVER_GRIP_LABEL = "over-grip alarm"

# Keyed by `GraspState.value` (a plain string) rather than the enum, so this label
# surface has no import dependency on the grasp module and the two cannot form a cycle.
GRASP_STATE_LABELS: dict[str, str] = {
    "released": GRASP_STATE_RELEASED_LABEL,
    "grasping": GRASP_STATE_GRASPING_LABEL,
    "over_grip": GRASP_STATE_OVER_GRIP_LABEL,
}

# The exhaustive set of user-facing grasp strings the static check scans. A new
# user-facing label must be added here so acceptance ④ keeps covering it.
USER_FACING_GRASP_LABELS: tuple[str, ...] = (
    GRASP_FORCE_VALUE_LABEL,
    GRASP_STATE_RELEASED_LABEL,
    GRASP_STATE_GRASPING_LABEL,
    GRASP_STATE_OVER_GRIP_LABEL,
)
