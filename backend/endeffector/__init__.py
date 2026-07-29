"""Which end effector each arm carries — gripper, or the fixed spatula that replaces it.

Both builds stay supported. What separates them is one motor: the pinch gripper is CAN id
`0x08`, and the spatula build does not have it. Everything downstream that touches the bus asks
`motor_send_ids` rather than assuming eight, because polling a motor that is not there walks the
CAN controller to `ERROR-PASSIVE` and degrades the seven joints that are.

`profile` holds one arm's build and what follows from it; `rig` holds both arms' builds and
persists them next to the CAN channel binding. The default is the spatula build — see `rig` for
why that asymmetry is deliberate.
"""

from backend.endeffector.profile import (
    ARM_SLOT_WIDTH,
    GRIPPER_BUILD_SEND_IDS,
    GRIPPER_SEND_ID,
    GRIPPER_SLOT_INDEX,
    SPATULA_BUILD_SEND_IDS,
    EndEffector,
    EndEffectorError,
    EndEffectorProfile,
    gripper_build,
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

__all__ = [
    "ARM_SLOT_WIDTH",
    "GRIPPER_BUILD_SEND_IDS",
    "GRIPPER_SEND_ID",
    "GRIPPER_SLOT_INDEX",
    "RIG_FILENAME",
    "RIG_VERSION",
    "SIDES",
    "SIDE_LEFT",
    "SIDE_RIGHT",
    "SPATULA_BUILD_SEND_IDS",
    "EndEffector",
    "EndEffectorError",
    "EndEffectorProfile",
    "RigEndEffectors",
    "default_rig",
    "gripper_build",
    "load_rig",
    "rig_path",
    "save_rig",
    "spatula_build",
]
