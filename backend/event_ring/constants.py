"""Fixed axes and window defaults of the WP-2C-09 event ring.

The two axes of the event dump are the joint axis and the channel axis (`02b` §3
WP-2C-09 fixes them at eight joints by eight channels). The joint count is derived
from the dynamics joint layout rather than restated, so a change to the arm's
degrees of freedom moves one constant, not two. The channel axis lives in
`sample.py`, where the channel identities and their units are defined together.
"""

from __future__ import annotations

from backend.dynamics.constants import ARM_JOINT_COUNT

# `ARM_JOINT_COUNT` is re-exported deliberately: it is the derivation base for the
# joint axis here, and the monitor tracks exactly the arm joints, so this module is
# the one place a consumer reads the arm-joint count from for the event ring.
__all__ = [
    "ARM_JOINT_COUNT",
    "DEFAULT_POST_EVENT_SEC",
    "DEFAULT_PRE_EVENT_SEC",
    "EVENT_JOINT_COUNT",
    "GRIPPER_JOINT_INDEX",
    "GRIPPER_MOTOR_COUNT",
]

# The gripper is a single Damiao motor carried in the same MIT feedback stream as
# the seven arm joints (`q_urdf[8]`). The event dump records it alongside them so a
# post-event window is complete for the whole arm side.
GRIPPER_MOTOR_COUNT = 1

# Motors recorded per arm side: seven arm joints plus the gripper. This is the
# eight-joint axis of the WP-2C-09 dump.
EVENT_JOINT_COUNT = ARM_JOINT_COUNT + GRIPPER_MOTOR_COUNT

# The gripper motor is the last index. WP-2C-11 disables residual-based detection
# on it — there is no finger-dynamics model and the grasp reaction is a standing
# offset — so the model-error monitor excludes this index by default. The dump
# itself still records the gripper's channels; only the residual monitor skips it.
GRIPPER_JOINT_INDEX = EVENT_JOINT_COUNT - 1

# Acceptance ① (`02b` §3 WP-2C-09) requires at least two seconds each side of an
# event, retained losslessly. These are window defaults, not measured on-hardware
# values: the real loop rate (1 kHz, or the ≤625 Hz pattern-B clamp of
# NFR-SAF-001) and the ring capacity that rate implies are hardware-deferred and
# re-derived through `reverify` when a real capture exists.
DEFAULT_PRE_EVENT_SEC = 2.0
DEFAULT_POST_EVENT_SEC = 2.0
