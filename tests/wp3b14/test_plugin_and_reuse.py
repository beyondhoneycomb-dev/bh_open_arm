"""WP-3B-14 acceptance ③ — clutch, state machine and safety gate are the VR code path.

The KER is a LeRobot plugin (registered like the VR teleoperator) and a joint-angle
SOURCE only. It re-implements no clutch, One-Euro smoother, heartbeat/link-loss state
machine, or workspace wall — those are the source-agnostic pipeline (WP-3B-09/10) that
wraps a VR or KER source identically (05 §2.7). "Same code path" is proven here as:
the plugin adds no parallel safety path (zero re-implementation), and it exposes the
same frozen three-level tracking validity that pipeline's state machine consumes.
"""

from __future__ import annotations

import math
from pathlib import Path

from backend.teleop.ker import (
    RULE_REIMPLEMENTATION,
    KerReading,
    MockKerDevice,
    OpenArmKER,
    OpenArmKERConfig,
    check_package,
    check_source,
    classify_joint_validity,
)
from backend.teleop.ker.constants import KER_CONFIG_CLASS
from contracts.teleop import (
    FEEDBACK_FEATURES,
    KER_DIST_NAME,
    KER_TELEOP_TYPE,
    TeleopValidity,
    device_class_from_config_class,
    is_plugin_convention_compliant,
    require_plugin_convention,
    validity_envelope,
)

_KER_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "teleop" / "ker"
_BIMANUAL_ANGLES = tuple(float(value) for value in range(16))


def test_plugin_is_discoverable_like_the_vr_teleoperator() -> None:
    """The distribution name carries the teleoperator plugin prefix, so LeRobot finds it."""
    assert KER_DIST_NAME == "lerobot_teleoperator_openarm_ker"
    assert is_plugin_convention_compliant(KER_DIST_NAME)
    require_plugin_convention(KER_DIST_NAME)


def test_device_class_derives_from_the_config_class_name() -> None:
    """`OpenArmKERConfig` resolves to device class `OpenArmKER` (05 §2.3 fallback)."""
    assert OpenArmKER.__name__ == device_class_from_config_class(KER_CONFIG_CLASS)
    assert OpenArmKER.config_class.__name__ == KER_CONFIG_CLASS
    assert OpenArmKER.name == KER_TELEOP_TYPE


def test_no_force_feedback_channels_because_the_ker_is_motorless() -> None:
    """`feedback_features` is the empty frozen mapping — no force channel can exist."""
    teleop = OpenArmKER(OpenArmKERConfig())
    assert teleop.feedback_features == dict(FEEDBACK_FEATURES) == {}


def test_ker_reuses_the_frozen_three_level_validity_model() -> None:
    """KER tracking validity surfaces through the same OA-TEL codes a VR source uses."""
    stale = validity_envelope(TeleopValidity.STALE)
    invalid = validity_envelope(TeleopValidity.INVALID)
    assert stale is not None and stale.code == "OA-TEL-003"
    assert invalid is not None and invalid.code == "OA-TEL-002"
    assert validity_envelope(TeleopValidity.OK) is None
    assert TeleopValidity.OK.is_publishable
    assert TeleopValidity.STALE.is_publishable
    assert not TeleopValidity.INVALID.is_publishable


def test_non_finite_joint_frame_is_invalid_and_discarded() -> None:
    """A non-finite joint frame is INVALID — the shared gate discards it, as with VR poses."""
    assert classify_joint_validity((1.0, 2.0, 3.0)) is TeleopValidity.OK
    assert classify_joint_validity((1.0, math.nan, 3.0)) is TeleopValidity.INVALID
    assert not classify_joint_validity((math.inf,)).is_publishable


def test_get_action_exposes_the_reading_validity_to_the_state_machine() -> None:
    """`tracking_validity` follows the last frame's validity — the state machine's input."""
    teleop = OpenArmKER(OpenArmKERConfig(bimanual=True))
    teleop.device = MockKerDevice(
        [
            KerReading(_BIMANUAL_ANGLES, TeleopValidity.OK),
            KerReading(_BIMANUAL_ANGLES, TeleopValidity.STALE),
            KerReading(_BIMANUAL_ANGLES, TeleopValidity.INVALID),
        ]
    )
    teleop.connect()
    teleop.get_action()
    assert teleop.tracking_validity is TeleopValidity.OK
    teleop.get_action()
    assert teleop.tracking_validity is TeleopValidity.STALE
    teleop.get_action()
    assert teleop.tracking_validity is TeleopValidity.INVALID


def test_package_reimplements_no_pipeline_machinery() -> None:
    """The KER package defines no clutch/smoother/heartbeat/workspace machinery (static)."""
    reimpl = [v for v in check_package(_KER_PACKAGE_ROOT) if v.rule == RULE_REIMPLEMENTATION]
    assert reimpl == []


def test_reimplementation_ban_is_not_vacuous() -> None:
    """Defining a piece of the shared pipeline here trips the re-implementation ban."""
    for source in (
        "class OneEuroSmoother:\n    pass\n",
        "class ClutchGate:\n    pass\n",
        "def heartbeat_tick():\n    pass\n",
        "class WorkspaceWall:\n    pass\n",
    ):
        assert any(v.rule == RULE_REIMPLEMENTATION for v in check_source(source))


def test_teleoperator_holds_no_clutch_or_safety_state() -> None:
    """The plugin object exposes no clutch/smoother/heartbeat/workspace member."""
    teleop = OpenArmKER(OpenArmKERConfig())
    banned = ("clutch", "smoother", "heartbeat", "workspace", "wall", "oneeuro", "one_euro")
    members = [name.lower() for name in dir(teleop)]
    assert not [name for name in members if any(token in name for token in banned)]
