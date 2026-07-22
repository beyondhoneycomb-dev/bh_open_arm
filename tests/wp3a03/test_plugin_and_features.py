"""WP-3A-03 ① / ② — LeRobot unmodified plugin, and the flat action_features convention.

`02b` §5.2 WP-3A-03 ①: `--teleop.type=openarm_vr` loads with zero LeRobot lines
modified — the plugin is discovered by LeRobot's own third-party mechanism, and its
config/device class resolve through LeRobot's own fallback (`FR-TEL-001`/`002`/`003`).
②: `action_features` uses the flat `{key: type}` convention; the nested convention
reproduces the dataset-feature-creation failure (`FR-TEL-004`).
"""

from __future__ import annotations

import pytest

import contracts.teleop as tel
from contracts.prim import BIMANUAL_ACTION_DIM, SINGLE_ARM_ACTION_DIM


def test_vr_distribution_obeys_the_teleoperator_discovery_prefix() -> None:
    """The VR distribution name is auto-discovered, so no LeRobot edit is needed to load it."""
    assert tel.TELEOPERATOR_DIST_PREFIX == "lerobot_teleoperator_"
    assert tel.VR_DIST_NAME.startswith(tel.TELEOPERATOR_DIST_PREFIX)
    assert tel.is_plugin_convention_compliant(tel.VR_DIST_NAME)
    tel.require_plugin_convention(tel.VR_DIST_NAME)


def test_a_non_conforming_distribution_is_refused() -> None:
    """A name outside the prefix would never be imported, so its registration never runs."""
    with pytest.raises(tel.PluginConventionError):
        tel.require_plugin_convention("openarm_vr_teleop")


def test_teleop_type_and_device_class_resolve_through_lerobots_own_naming() -> None:
    """`--teleop.type=openarm_vr` and the OpenArmVRConfig -> OpenArmVR fallback are the contract."""
    assert tel.VR_TELEOP_TYPE == "openarm_vr"
    assert tel.VR_CONFIG_CLASS == "OpenArmVRConfig"
    assert tel.device_class_from_config_class(tel.VR_CONFIG_CLASS) == tel.VR_DEVICE_CLASS
    assert tel.VR_DEVICE_CLASS == "OpenArmVR"


def test_a_config_class_without_the_config_suffix_is_refused() -> None:
    """The fallback strips `Config`; a name without it would resolve to a missing class."""
    with pytest.raises(tel.PluginConventionError):
        tel.device_class_from_config_class("OpenArmVR")


def test_abstract_member_set_is_the_documented_teleoperator_surface() -> None:
    """The plugin must implement the full LeRobot Teleoperator ABC surface (FR-TEL-003)."""
    documented = {
        "action_features",
        "feedback_features",
        "is_connected",
        "connect",
        "is_calibrated",
        "calibrate",
        "configure",
        "get_action",
        "send_feedback",
        "disconnect",
    }
    assert documented == tel.ABSTRACT_MEMBERS


def test_abstract_member_set_equals_the_installed_lerobot_abc() -> None:
    """When LeRobot is installed, our surface equals its ABC exactly — a drop-in, no fork."""
    teleoperator = pytest.importorskip("lerobot.teleoperators.teleoperator")
    abc_members = frozenset(teleoperator.Teleoperator.__abstractmethods__)
    assert abc_members == tel.ABSTRACT_MEMBERS


def test_flat_action_features_is_the_accepted_convention() -> None:
    """Flat `{key: type}` is convention (a); dataset feature creation returns the flat dict."""
    features = {"left_joint_1.pos": float, "left_joint_1.vel": float, "left_joint_1.torque": float}
    assert tel.feature_convention(features) == tel.FEATURE_CONVENTION_FLAT
    assert tel.is_flat_action_features(features)
    assert tel.aggregate_dataset_action_features(features) == features


def test_nested_action_features_reproduces_the_dataset_feature_failure() -> None:
    """The nested `{dtype,shape,names}` convention (b) fails dataset feature creation."""
    nested = {"action": {"dtype": "float32", "shape": [BIMANUAL_ACTION_DIM], "names": ["j"]}}
    assert tel.feature_convention(nested) == tel.FEATURE_CONVENTION_NESTED
    assert not tel.is_flat_action_features(nested)
    with pytest.raises(tel.FeatureConventionError):
        tel.aggregate_dataset_action_features(nested)


def test_position_dimension_count_is_consumed_from_the_ctr_prim_action_shape() -> None:
    """The `.pos` width is CTR-PRIM's action shape (8 single-arm / 16 bimanual), not restated."""
    bimanual = {f"j{i}.pos": float for i in range(BIMANUAL_ACTION_DIM)}
    single = {f"j{i}.pos": float for i in range(SINGLE_ARM_ACTION_DIM)}
    assert tel.position_key_count(bimanual) == BIMANUAL_ACTION_DIM
    assert tel.is_action_dim_position_only(bimanual)
    assert tel.is_action_dim_position_only(single)
    assert not tel.is_action_dim_position_only({f"j{i}.pos": float for i in range(7)})


def test_non_position_dimensions_must_be_honest_zeros() -> None:
    """A VR teleoperator has no torque source; `.vel`/`.torque` must be zero (FR-TEL-064)."""
    action = {"left_joint_1.pos": 12.5, "left_joint_1.vel": 0.0, "left_joint_1.torque": 0.0}
    tel.verify_non_position_dims_zero(action)
    with pytest.raises(tel.FeatureConventionError):
        tel.verify_non_position_dims_zero({"left_joint_1.torque": 3.1})
