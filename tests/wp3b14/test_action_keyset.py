"""WP-3B-14 acceptance ② — the action keyset: position-only with honest zeros.

The KER follows the §2.5 action keyset exactly: `.pos` carries the joint angle in
degrees and `.vel`/`.torque` are honest zeros (FR-TEL-064). When the paired follower
records velocity and torque, those columns must be present with value zero, or
`build_dataset_frame` raises a KeyError (05 §2.5); when it does not, the keyset is the
position-only training target.
"""

from __future__ import annotations

from backend.teleop.ker import (
    MockKerDevice,
    OpenArmKER,
    OpenArmKERConfig,
    ker_action_features,
)
from contracts.prim import BIMANUAL_ACTION_DIM, SINGLE_ARM_ACTION_DIM
from contracts.teleop import (
    TeleopValidity,
    is_action_dim_position_only,
    position_key_count,
    verify_non_position_dims_zero,
)

_BIMANUAL_ANGLES = tuple(float(value) for value in range(16))


def test_position_only_keyset_when_velocity_torque_off() -> None:
    """With the switch off the keyset is the 16 position channels only."""
    features = ker_action_features(bimanual=True, use_velocity_and_torque=False)
    assert position_key_count(features) == BIMANUAL_ACTION_DIM
    assert all(key.endswith(".pos") for key in features)
    assert is_action_dim_position_only(features)


def test_single_arm_position_keyset_is_eight() -> None:
    """The single-arm position keyset is 8 channels (05 §2.5)."""
    features = ker_action_features(bimanual=False, use_velocity_and_torque=False)
    assert position_key_count(features) == SINGLE_ARM_ACTION_DIM


def test_honest_zero_columns_present_when_switch_on() -> None:
    """With the switch on the keyset carries `.vel`/`.torque` columns beside `.pos`."""
    features = ker_action_features(bimanual=True, use_velocity_and_torque=True)
    assert position_key_count(features) == BIMANUAL_ACTION_DIM
    assert any(key.endswith(".vel") for key in features)
    assert any(key.endswith(".torque") for key in features)
    assert len(features) == 3 * BIMANUAL_ACTION_DIM


def test_get_action_non_position_dims_are_zero() -> None:
    """Every emitted `.vel`/`.torque` value is the honest zero (FR-TEL-064)."""
    teleop = OpenArmKER(OpenArmKERConfig(bimanual=True, use_velocity_and_torque=True))
    teleop.device = MockKerDevice.constant(_BIMANUAL_ANGLES, TeleopValidity.OK)
    teleop.connect()
    action = teleop.get_action()
    verify_non_position_dims_zero(action)
    assert all(value == 0.0 for key, value in action.items() if not key.endswith(".pos"))


def test_get_action_keys_match_action_features_exactly() -> None:
    """`get_action()` returns exactly the `action_features` keys (no missing-key KeyError)."""
    teleop = OpenArmKER(OpenArmKERConfig(bimanual=True, use_velocity_and_torque=True))
    teleop.device = MockKerDevice.constant(_BIMANUAL_ANGLES, TeleopValidity.OK)
    teleop.connect()
    assert set(teleop.get_action()) == set(teleop.action_features)
