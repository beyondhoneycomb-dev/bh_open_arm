"""Which tool each arm carries — an open registry, and what follows from the fitted one.

Today: the v2 pinch gripper and a fixed spatula. More are expected, so a tool is a row in
`tools.TOOL_REGISTRY` rather than a branch; consumers ask what a tool *does* (`gripper_motor`)
instead of which one it *is*.

One capability drives the rest and it is electrical: whether CAN id `0x08` is a motor on that
arm. Polling one that is not there walks the controller to `ERROR-PASSIVE` and degrades the seven
joints that are, so `motor_send_ids` — not the eight-motor registration — is the polling truth.

Tool mass is optional throughout. It cannot be measured with torque off, so requiring it would
block work that has nothing to do with mass; `payload_mass_kg()` is the one place that refuses.
"""

from backend.endeffector.profile import (
    EndEffectorProfile,
    default_profile,
    gripper_build,
    profile_for,
    spatula_build,
)
from backend.endeffector.rig import (
    RIG_FILENAME,
    RIG_VERSION,
    SIDE_LEFT,
    SIDE_RIGHT,
    SIDES,
    RigEndEffectors,
    default_rig,
    load_rig,
    rig_path,
    save_rig,
)
from backend.endeffector.tools import (
    ARM_JOINT_SEND_IDS,
    ARM_SLOT_WIDTH,
    DEFAULT_TOOL_ID,
    GRIPPER_SEND_ID,
    GRIPPER_SLOT_INDEX,
    TOOL_FIXED_SPATULA,
    TOOL_GRIPPER,
    TOOL_REGISTRY,
    EndEffectorError,
    ToolDefinition,
    registered_tools,
    tool_by_id,
)

__all__ = [
    "ARM_JOINT_SEND_IDS",
    "ARM_SLOT_WIDTH",
    "DEFAULT_TOOL_ID",
    "GRIPPER_SEND_ID",
    "GRIPPER_SLOT_INDEX",
    "RIG_FILENAME",
    "RIG_VERSION",
    "SIDES",
    "SIDE_LEFT",
    "SIDE_RIGHT",
    "TOOL_FIXED_SPATULA",
    "TOOL_GRIPPER",
    "TOOL_REGISTRY",
    "EndEffectorError",
    "EndEffectorProfile",
    "RigEndEffectors",
    "ToolDefinition",
    "default_profile",
    "default_rig",
    "gripper_build",
    "load_rig",
    "profile_for",
    "registered_tools",
    "rig_path",
    "save_rig",
    "spatula_build",
    "tool_by_id",
]
