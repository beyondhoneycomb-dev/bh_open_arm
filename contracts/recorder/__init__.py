"""CTR-REC@v1 — the recorder dataset feature-set contract (public surface).

The recorder schema consumes `CTR-PRIM@v1` (action payload shape, camera
identifier, frame-type tag, timestamp domain) and freezes the LeRobot dataset
shape a recording produces (`02b` §5.2 WP-3A-05). Everything importable here is
defined in `contracts/recorder/schema.py`; the frozen canonical body
(`contracts/recorder/schema.json`, `CONTRACT_FROZEN`) is materialised from
`frozen_json_text()` and locked by `WP-3A-06`.
"""

from __future__ import annotations

from contracts.recorder.schema import (
    ACTION_KEY,
    CONSUMED_CONTRACTS,
    CONTRACT_ID,
    DEFAULT_USE_VELOCITY_AND_TORQUE,
    META_FEATURES,
    MOTOR_NAMES,
    MOTORS_PER_ARM,
    OBSERVATION_STATE_KEY,
    PER_MOTOR_SUFFIXES_FULL,
    PER_MOTOR_SUFFIXES_MIN,
    POSITION_SUFFIX,
    SCHEMA_VERSION,
    SUFFIX_UNITS,
    TIMESTAMP_DOMAIN,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    RecorderConfig,
    RecorderContractError,
    action_dim,
    action_names,
    allowed_info_keys,
    channels_with_suffix,
    feature_set,
    frozen_document,
    frozen_json_text,
    image_feature_keys,
    index_of,
    motor_keys,
    observation_state_names,
    push_to_hub_decision,
    resolve_velocity_torque_switch,
    unit_convention,
    validate_info_features,
    write_frozen_json,
)
from ops.hubguard.push_policy import ENFORCED_PUSH_TO_HUB_DEFAULT

__all__ = [
    "ACTION_KEY",
    "CONSUMED_CONTRACTS",
    "CONTRACT_ID",
    "DEFAULT_USE_VELOCITY_AND_TORQUE",
    "ENFORCED_PUSH_TO_HUB_DEFAULT",
    "META_FEATURES",
    "MOTORS_PER_ARM",
    "MOTOR_NAMES",
    "OBSERVATION_STATE_KEY",
    "PER_MOTOR_SUFFIXES_FULL",
    "PER_MOTOR_SUFFIXES_MIN",
    "POSITION_SUFFIX",
    "SCHEMA_VERSION",
    "SUFFIX_UNITS",
    "TIMESTAMP_DOMAIN",
    "TORQUE_SUFFIX",
    "VELOCITY_SUFFIX",
    "RecorderConfig",
    "RecorderContractError",
    "action_dim",
    "action_names",
    "allowed_info_keys",
    "channels_with_suffix",
    "feature_set",
    "frozen_document",
    "frozen_json_text",
    "image_feature_keys",
    "index_of",
    "motor_keys",
    "observation_state_names",
    "push_to_hub_decision",
    "resolve_velocity_torque_switch",
    "unit_convention",
    "validate_info_features",
    "write_frozen_json",
]
