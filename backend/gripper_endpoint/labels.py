"""User-facing labels for the gripper POS_FORCE surface — per-unit only.

Grip force is exposed as `torque_pu` in [0, 1] (per-unit). The per-unit-to-force
conversion constant is undetermined (`12` §5-Q14) and no load cell is used, so a
physical force unit would assert a calibration we do not have (FR-MAN-016,
FR-SAF-024b). Every string a user sees for gripper force originates here, and the
WP-2A-08 static check scans this surface — and the whole package's string
literals — to confirm no physical force unit label ever reaches the UI.
"""

from __future__ import annotations

FORCE_CAP_LABEL = "grip force cap (per-unit)"
FORCE_VALUE_LABEL = "grip force (per-unit, 0-1)"
SPEED_CAP_LABEL = "gripper speed cap (rad/s)"
OPEN_LABEL = "open"
CLOSE_LABEL = "close"

# The exhaustive set of user-facing gripper strings the static check scans. A new
# user-facing label must be added here so acceptance (3) keeps covering it. The list
# of forbidden physical-force-unit tokens lives in the WP-2A-08 static check, not
# here, so this package carries no such token in any string literal of its own.
USER_FACING_LABELS: tuple[str, ...] = (
    FORCE_CAP_LABEL,
    FORCE_VALUE_LABEL,
    SPEED_CAP_LABEL,
    OPEN_LABEL,
    CLOSE_LABEL,
)
