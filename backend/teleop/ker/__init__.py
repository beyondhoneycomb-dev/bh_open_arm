"""KER teleoperator — a LeRobot plugin that streams joint angles, no IK (WP-3B-14).

The KER (Kinematic Equivalent Replica) is a motorless leader arm read over USB
(Espressif ESP32-S3, VID 0x303A / PID 0x4002). This package wraps it as a LeRobot
`Teleoperator` (FR-TEL-062): `get_action()` returns the read joint angles directly as
`.pos` degrees with honest-zero `.vel`/`.torque` (FR-TEL-064, NO IK), and it opens no
CAN channel (FR-TEL-063), so inserting it changes no CAN DAG.

It consumes the frozen CTR-TEL@v1 reserved KER slot and re-implements none of the
clutch, tracking state machine, or safety gate — those are the source-agnostic
pipeline (WP-3B-09/10) that wraps a VR or KER source identically (05 §2.7). Real USB
I/O is deferred and re-verified on hardware through `reverify`.
"""

from __future__ import annotations

from backend.teleop.ker.config import OpenArmKERConfig
from backend.teleop.ker.constants import (
    KER_CONFIG_CLASS,
    KER_FORCE_FEEDBACK_UNAVAILABLE_NOTICE,
    KER_UI_LABEL,
    MOCK_NEUTRAL_JOINT_DEG,
)
from backend.teleop.ker.device import (
    KerDevice,
    KerDeviceUnavailableError,
    KerReading,
    MockKerDevice,
    UsbKerDevice,
    classify_joint_validity,
    module_available,
)
from backend.teleop.ker.keyset import (
    KerKeysetError,
    ker_action,
    ker_action_features,
    position_channel_names,
)
from backend.teleop.ker.reverify import (
    ReverifyResult,
    real_device_available,
    reverify_no_ik_and_zero_can,
    verify_reading_is_ik_free,
)
from backend.teleop.ker.staticcheck import (
    RULE_CAN_SYMBOL,
    RULE_CLI_SPAWN,
    RULE_FORBIDDEN_TOKEN,
    RULE_IK,
    RULE_INTREE_LOOP_IMPORT,
    RULE_REIMPLEMENTATION,
    Violation,
    check_package,
    check_source,
    scan_forbidden_token,
)
from backend.teleop.ker.teleoperator import OpenArmKER

__all__ = [
    "KER_CONFIG_CLASS",
    "KER_FORCE_FEEDBACK_UNAVAILABLE_NOTICE",
    "KER_UI_LABEL",
    "MOCK_NEUTRAL_JOINT_DEG",
    "RULE_CAN_SYMBOL",
    "RULE_CLI_SPAWN",
    "RULE_FORBIDDEN_TOKEN",
    "RULE_IK",
    "RULE_INTREE_LOOP_IMPORT",
    "RULE_REIMPLEMENTATION",
    "KerDevice",
    "KerDeviceUnavailableError",
    "KerKeysetError",
    "KerReading",
    "MockKerDevice",
    "OpenArmKER",
    "OpenArmKERConfig",
    "ReverifyResult",
    "UsbKerDevice",
    "Violation",
    "check_package",
    "check_source",
    "classify_joint_validity",
    "ker_action",
    "ker_action_features",
    "module_available",
    "position_channel_names",
    "real_device_available",
    "reverify_no_ik_and_zero_can",
    "scan_forbidden_token",
    "verify_reading_is_ik_free",
]
