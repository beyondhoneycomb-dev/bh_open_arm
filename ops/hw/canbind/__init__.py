"""Stable per-arm CAN identity without renaming interfaces (WP-0B-05, second mechanism).

udev rules are the first mechanism and stay available. This package is the one that works on a
rig whose adapter reports no serial: enumerate channels as the kernel named them, key each by
`(ID_PATH, dev_id)`, and settle which arm is which by having the operator move an arm while
watching which channel's joints respond.

Three modules, three separable jobs:

  * `discovery` — what channels exist, and their reboot-stable key. No root, no sockets.
  * `identify` — which arm is on which channel, decided by physical motion rather than by
    anything readable on the bus (`03` §2.1 makes the arms indistinguishable there).
  * `binding` — persist that answer and re-check it every start, refusing to guess when the
    channels present no longer match the ones the answer was recorded against.
"""

from ops.hw.canbind.binding import (
    BINDING_FILENAME,
    BINDING_VERSION,
    ArmRole,
    BindingCheck,
    BindingError,
    ChannelBinding,
    binding_path,
    check_binding,
    load_binding,
    save_binding,
)
from ops.hw.canbind.discovery import (
    CanChannel,
    bring_up_command,
    list_can_channels,
)
from ops.hw.canbind.identify import (
    MOTION_THRESHOLD_RAD,
    QUIET_THRESHOLD_RAD,
    ChannelMotion,
    IdentificationError,
    IdentificationResult,
    identify_moved_channel,
    judge,
    measure_motion,
    read_baseline,
)

__all__ = [
    "BINDING_FILENAME",
    "BINDING_VERSION",
    "MOTION_THRESHOLD_RAD",
    "QUIET_THRESHOLD_RAD",
    "ArmRole",
    "BindingCheck",
    "BindingError",
    "CanChannel",
    "ChannelBinding",
    "ChannelMotion",
    "IdentificationError",
    "IdentificationResult",
    "binding_path",
    "bring_up_command",
    "check_binding",
    "identify_moved_channel",
    "judge",
    "list_can_channels",
    "load_binding",
    "measure_motion",
    "read_baseline",
    "save_binding",
]
