"""CTR-REC@v1 acceptance: the six WP-3A-05 runs and the two FAIL_BLOCKING defects.

`02b` §5.2 WP-3A-05 numbers the checks this file proves: ① `use_velocity_and_torque`
does not widen `action`, ② no out-of-contract key reaches `info.json`, ③ consumers
address channels by name suffix with zero hardcoded indices, ④ the mixed units are
recorded in meta, ⑤ `push_to_hub` defaults to false, ⑥ the switch is a single
follower+leader control. The blocking pair: a torque dimension entering `action`,
and an independently settable per-side switch.
"""

from __future__ import annotations

import dataclasses

import pytest

import contracts.prim as prim
import contracts.recorder as rec


def _bimanual_full() -> rec.RecorderConfig:
    """A two-arm config with velocity and torque enabled (the 48-dim case)."""
    return rec.RecorderConfig(bimanual=True, use_velocity_and_torque=True)


# --- ① use_velocity_and_torque never widens action ------------------------


@pytest.mark.parametrize("bimanual", [False, True])
@pytest.mark.parametrize("use_vt", [False, True])
def test_action_width_is_position_only_regardless_of_switch(bimanual: bool, use_vt: bool) -> None:
    """action stays 8/16 whether or not velocity/torque are recorded (`02b` ①)."""
    config = rec.RecorderConfig(bimanual=bimanual, use_velocity_and_torque=use_vt)
    expected = prim.BIMANUAL_ACTION_DIM if bimanual else prim.SINGLE_ARM_ACTION_DIM
    names = rec.action_names(bimanual)
    assert rec.action_dim(bimanual) == expected
    assert len(names) == expected
    assert all(name.endswith(rec.POSITION_SUFFIX) for name in names)
    assert rec.feature_set(config)[rec.ACTION_KEY]["shape"] == [expected]


def test_observation_state_widens_with_switch_but_action_does_not() -> None:
    """The switch moves observation.state to 48 while action holds at 16 (`02b` ①)."""
    assert len(rec.observation_state_names(True, True)) == 48
    assert len(rec.observation_state_names(True, False)) == 16
    assert rec.action_dim(True) == 16


# --- ② the info.json key set is closed ------------------------------------


def test_feature_set_keys_are_exactly_the_allowed_set() -> None:
    """feature_set produces no key outside allowed_info_keys (`02b` ②)."""
    config = _bimanual_full()
    features = rec.feature_set(config)
    assert set(features) == rec.allowed_info_keys(config)


def test_out_of_contract_key_is_rejected() -> None:
    """A stray info.json key fails validation (`02b` ②)."""
    config = _bimanual_full()
    features = dict(rec.feature_set(config))
    features["observation.effort"] = {"dtype": "float32", "shape": [16]}
    with pytest.raises(rec.RecorderContractError, match="out-of-contract"):
        rec.validate_info_features(features, config)


def test_clean_feature_set_validates() -> None:
    """The feature set the contract builds passes its own validator."""
    config = _bimanual_full()
    rec.validate_info_features(rec.feature_set(config), config)


def test_camera_image_keys_come_from_prim_slot_join() -> None:
    """observation.images.<slot> keys are the CTR-PRIM join, RGB then depth (`02b` ②)."""
    wrist = prim.arm_slot("left", "wrist")
    top = prim.sim_slot("overhead")
    config = rec.RecorderConfig(
        bimanual=True, camera_slots=(wrist, top), depth_slots=frozenset({wrist})
    )
    keys = rec.image_feature_keys(config)
    assert wrist.image_key() in keys
    assert wrist.depth_key() in keys
    assert top.image_key() in keys
    assert top.depth_key() not in keys
    assert set(keys) <= rec.allowed_info_keys(config)


def test_depth_slot_must_be_an_rgb_slot() -> None:
    """A depth-only slot with no RGB registration is refused."""
    orphan = prim.arm_slot("right", "wrist")
    with pytest.raises(rec.RecorderContractError):
        rec.RecorderConfig(bimanual=True, camera_slots=(), depth_slots=frozenset({orphan}))


# --- ③ address by suffix, never by hardcoded index ------------------------


def test_torque_channel_is_found_by_name_not_index() -> None:
    """index_of returns the interleaved position derived from names, not a literal (`02b` ③)."""
    names = rec.observation_state_names(True, True)
    for block, side in ((0, "left"), (24, "right")):
        for motor_index, motor in enumerate(rec.MOTOR_NAMES):
            key = f"{side}_{motor}"
            expected = block + rec.MOTORS_PER_ARM * 0 + motor_index * 3 + 2
            assert rec.index_of(names, key, rec.TORQUE_SUFFIX) == expected
            assert names[expected] == f"{key}{rec.TORQUE_SUFFIX}"


def test_index_lookup_tracks_the_switch() -> None:
    """The same name resolves to a different index when the switch changes width (`02b` ③)."""
    full = rec.observation_state_names(False, True)
    minimal = rec.observation_state_names(False, False)
    assert rec.index_of(full, "gripper", rec.POSITION_SUFFIX) == 21
    assert rec.index_of(minimal, "gripper", rec.POSITION_SUFFIX) == 7


def test_absent_channel_lookup_raises_rather_than_guessing() -> None:
    """Querying a torque channel a position-only dataset never wrote fails loudly (`02b` ③)."""
    minimal = rec.observation_state_names(True, False)
    with pytest.raises(rec.RecorderContractError):
        rec.index_of(minimal, "left_joint_1", rec.TORQUE_SUFFIX)


def test_channels_with_suffix_selects_by_string() -> None:
    """Torque channels are selected by suffix match, one per motor when enabled."""
    names = rec.observation_state_names(True, True)
    assert len(rec.channels_with_suffix(names, rec.TORQUE_SUFFIX)) == rec.MOTORS_PER_ARM * 2
    assert rec.channels_with_suffix(names, rec.TORQUE_SUFFIX) == tuple(
        i for i, n in enumerate(names) if n.endswith(rec.TORQUE_SUFFIX)
    )


# --- ④ mixed units recorded in meta ---------------------------------------


def test_unit_convention_records_the_mixed_units() -> None:
    """meta carries deg / deg/s / Nm per suffix (`02b` ④)."""
    units = rec.unit_convention()
    assert units[rec.POSITION_SUFFIX] == "deg"
    assert units[rec.VELOCITY_SUFFIX] == "deg/s"
    assert units[rec.TORQUE_SUFFIX] == "Nm"
    assert rec.frozen_document()["unit_convention"] == units


def test_position_unit_is_consumed_from_prim() -> None:
    """The .pos unit is CTR-PRIM's action unit, not a restated literal (`02b` §5.0b)."""
    assert rec.unit_convention()[rec.POSITION_SUFFIX] == prim.ACTION_POSITION_UNIT


# --- ⑤ push_to_hub defaults to false, via the WP-OPS-04 guard -------------


def test_push_to_hub_unspecified_resolves_false() -> None:
    """An unspecified push_to_hub resolves to false through the hub guard (`02b` ⑤)."""
    decision = rec.push_to_hub_decision(rec.RecorderConfig(bimanual=False))
    assert decision.push_to_hub is False
    assert rec.ENFORCED_PUSH_TO_HUB_DEFAULT is False


def test_push_to_hub_request_without_confirmation_is_suppressed() -> None:
    """A bare request with no confirmation does not upload — the guard suppresses it (`02b` ⑤)."""
    decision = rec.push_to_hub_decision(rec.RecorderConfig(bimanual=False, push_to_hub=True))
    assert decision.push_to_hub is False
    assert decision.suppressed is True


# --- ⑥ one switch for follower and leader ---------------------------------


def test_switch_is_a_single_follower_and_leader_control() -> None:
    """Equal follower/leader values collapse to one; disagreement is refused (`02b` ⑥)."""
    assert rec.resolve_velocity_torque_switch(True, True) is True
    assert rec.resolve_velocity_torque_switch(False, False) is False
    with pytest.raises(rec.RecorderContractError, match="single follower\\+leader switch"):
        rec.resolve_velocity_torque_switch(True, False)


def test_config_exposes_exactly_one_velocity_torque_field() -> None:
    """The config models the switch once — no separate leader/follower fields exist (`02b` ⑥)."""
    names = {f.name for f in dataclasses.fields(rec.RecorderConfig)}
    switch_fields = {n for n in names if "velocity" in n or "torque" in n}
    assert switch_fields == {"use_velocity_and_torque"}


# --- FAIL_BLOCKING: a torque dimension entering action --------------------


def test_action_carrying_a_torque_name_is_fail_blocking() -> None:
    """An action feature with a .torque name is rejected (`02b` §5.2 negative branch)."""
    config = _bimanual_full()
    features = dict(rec.feature_set(config))
    action_body = dict(features[rec.ACTION_KEY])
    action_body["names"] = [*action_body["names"], "left_joint_1.torque"]
    action_body["shape"] = [len(action_body["names"])]
    features[rec.ACTION_KEY] = action_body
    with pytest.raises(rec.RecorderContractError, match="non-position dimensions"):
        rec.validate_info_features(features, config)


def test_action_widened_to_observation_state_is_rejected() -> None:
    """Recording the 48-dim state vector as action fails — action is position only."""
    config = _bimanual_full()
    features = dict(rec.feature_set(config))
    features[rec.ACTION_KEY] = {
        "dtype": "float32",
        "shape": [48],
        "names": list(rec.observation_state_names(True, True)),
    }
    with pytest.raises(rec.RecorderContractError):
        rec.validate_info_features(features, config)


# --- consumption identity: the timestamp meta is the synthetic grid -------


def test_timestamp_meta_is_the_synthetic_grid_domain() -> None:
    """The timestamp meta is CTR-PRIM's synthetic-grid domain, not a capture instant."""
    assert rec.TIMESTAMP_DOMAIN == prim.TimestampDomain.SYNTHETIC_GRID
    assert rec.frozen_document()["timestamp_domain"] == prim.TimestampDomain.SYNTHETIC_GRID.value
    assert "timestamp" in rec.META_FEATURES
