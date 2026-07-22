"""KER teleoperator literals the frozen CTR-TEL contract does not carry (WP-3B-14).

The USB identity, transport, CAN-channel count and IK flag are consumed from
`contracts.teleop` (CTR-TEL@v1) and are never restated here. This module holds only
the KER-specific values the contract has no place for: the GUI descriptor text, the
force-feedback-unavailable notice, the plugin config class name, and the offline
mock's neutral joint value.
"""

from __future__ import annotations

# The GUI descriptor for the KER leader (FR-TEL-065, 05 §2.12). The device enumerates
# under Espressif's USB vendor id (0x303A = ESP32-S3), so the label names that
# silicon; the vendor scan (acceptance ④) rejects the wrong vendor name elsewhere.
# Korean is operator-facing UI content, not a code comment.
KER_UI_LABEL = "ESP32-S3 기반 USB 인코더 모듈"

# The operator notice that bilateral force feedback is impossible on the KER
# (FR-TEL-065, acceptance ⑤): the leader is motorless, so no torque channel exists to
# reflect — the absence is a hardware fact, not a configuration choice. Korean is UI
# content shown to the operator at session start.
KER_FORCE_FEEDBACK_UNAVAILABLE_NOTICE = (
    "KER은 모터가 없는 리더암이라 바이래터럴 힘 피드백이 원천 불가능합니다."
)

# The plugin config class name. LeRobot's fallback resolver derives the device class
# by stripping the `Config` suffix (05 §2.3), so the derived device class is
# `OpenArmKER`; naming the config class once keeps that derivation checkable.
KER_CONFIG_CLASS = "OpenArmKERConfig"

# The offline mock's neutral joint angle (degrees). Zero is a well-formed,
# deterministic stand-in — never streamed from real hardware (see MockKerDevice); the
# real reader fails loudly rather than defaulting to this (never fake a real read).
MOCK_NEUTRAL_JOINT_DEG = 0.0
