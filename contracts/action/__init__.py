"""CTR-ACT@v1 — the frozen action/observation channel schema and its enforcement.

The public surface of the action/observation contract. Consumers import the six
channel types, the schema loader and validators, the audit-vs-training separation
rules, and the freeze/version guard from here. The frozen declaration itself is
`contracts/action_observation.yaml`; this package reads and enforces it.

Nothing here imports the robot stack, so the whole contract runs in the light
lane. The Robot plugin ABC (CTR-PLUG@v1), which does import LeRobot, lives in
`contracts.plugin.robot_abc` and is imported explicitly by its consumers.
"""

from __future__ import annotations

from contracts.action.channels import (
    BIMANUAL_ACTION_DIM,
    MIT_COMMAND_FIELDS,
    SINGLE_ARM_ACTION_DIM,
    AcceptedPositionAction,
    ClampReason,
    ExecutedMitCommand,
    RequestedPositionAction,
    SafetyOverride,
)
from contracts.action.checker import (
    RULE_TORQUE_IN_ACTION_TARGET,
    Violation,
    check_action_target_source,
)
from contracts.action.observation import (
    BIMANUAL_OBSERVATION_DIM,
    DROP_COUNTER_META,
    SINGLE_ARM_OBSERVATION_DIM,
    raw_observation_channels,
    raw_observation_dim,
)
from contracts.action.schema import (
    ACTION_TARGET_CHANNELS,
    AUDIT_ONLY_CHANNELS,
    CONTRACT_ID,
    CONTRACT_PATH,
    REQUIRED_CHANNELS,
    TRAINING_TARGET_CHANNEL,
    ActionObservationSchema,
    ChannelSpec,
    is_audit_only,
    load_schema,
    parse_schema,
    validate_frame,
    validate_schema,
)
from contracts.action.version import (
    VersionVerdict,
    check_version_bump,
    schema_digest,
    verify_frozen_digest,
)

__all__ = [
    "ACTION_TARGET_CHANNELS",
    "AUDIT_ONLY_CHANNELS",
    "BIMANUAL_ACTION_DIM",
    "BIMANUAL_OBSERVATION_DIM",
    "CONTRACT_ID",
    "CONTRACT_PATH",
    "DROP_COUNTER_META",
    "MIT_COMMAND_FIELDS",
    "REQUIRED_CHANNELS",
    "RULE_TORQUE_IN_ACTION_TARGET",
    "SINGLE_ARM_ACTION_DIM",
    "SINGLE_ARM_OBSERVATION_DIM",
    "TRAINING_TARGET_CHANNEL",
    "AcceptedPositionAction",
    "ActionObservationSchema",
    "ChannelSpec",
    "ClampReason",
    "ExecutedMitCommand",
    "RequestedPositionAction",
    "SafetyOverride",
    "VersionVerdict",
    "Violation",
    "check_action_target_source",
    "check_version_bump",
    "is_audit_only",
    "load_schema",
    "parse_schema",
    "raw_observation_channels",
    "raw_observation_dim",
    "schema_digest",
    "validate_frame",
    "validate_schema",
    "verify_frozen_digest",
]
