"""Load and validate the frozen CTR-ACT@v1 channel schema.

`contracts/action_observation.yaml` is the frozen declaration of the six channels,
their units, and the one rule that keeps audit apart from training: exactly one
channel is the training target and it is position-only, while the executed MIT
command and the safety metadata are audit-only and may never be a target.

This module reads that table and enforces the structural invariants (WP-0A-02
acceptance ①-⑦ minus the type-level ones the tag types already hold). It also
holds `validate_frame`, the runtime rule that a recorded frame carrying the
accepted action without the request — or the reverse — is rejected, because a
post-clamp-only record erases the information intervention debugging needs
(00 §8.3, acceptance ②).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from contracts.action.channels import BIMANUAL_ACTION_DIM
from contracts.action.observation import BIMANUAL_OBSERVATION_DIM

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "action_observation.yaml"

CONTRACT_ID = "CTR-ACT@v1"

# The six channel names SPINE §6 freezes; the schema must declare exactly these.
REQUIRED_CHANNELS = (
    "requestedPositionAction",
    "acceptedPositionAction",
    "executedMitCommand",
    "safetyOverride",
    "rawObservation",
    "trainingFeatureProjection",
)

# The two action-target channels; both are position-only in `Deg`. A torque unit
# here is the audit-into-training leak the contract exists to forbid.
ACTION_TARGET_CHANNELS = ("requestedPositionAction", "acceptedPositionAction")

# The channel that is the training action target (position-only, post-clamp).
TRAINING_TARGET_CHANNEL = "acceptedPositionAction"

# Channels that are audit/diagnostic and may never be a training target (00 §8.3).
AUDIT_ONLY_CHANNELS = ("executedMitCommand", "safetyOverride")

# The unit each declared physical MIT field must carry (12 §2.7). kp/kd are gains
# and are absent here on purpose — they are not CTR-UNIT quantities.
MIT_FIELD_UNITS = {"q": "Rad", "dq": "RadPerSec", "tau": "Nm"}

_POSITION_UNIT = "Deg"


@dataclass(frozen=True)
class ChannelSpec:
    """One declared channel of the frozen schema.

    Attributes:
        name: Channel name, e.g. `acceptedPositionAction`.
        role: What the channel is for, e.g. `action_accepted`, `audit`.
        unit: Declared unit tag when the whole channel is one physical quantity,
            or empty when the channel is a struct or has no single unit.
        dim: Declared dimension, or None when the channel is not a fixed vector.
        position_only: Whether the channel is position-only.
        training_target: Whether the channel is the training action target.
        fields: Sub-field declarations for struct channels (MIT, safety).
    """

    name: str
    role: str
    unit: str
    dim: int | None
    position_only: bool
    training_target: bool
    fields: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ActionObservationSchema:
    """The parsed frozen action/observation schema.

    Attributes:
        contract: Contract id and generation, e.g. `CTR-ACT@v1`.
        frozen_digest: The pinned content digest of the frozen core.
        channels: Declared channels, in file order.
        training_target_channel: The single channel that is the training target.
        audit_only_channels: Channels forbidden from being a training target.
    """

    contract: str
    frozen_digest: str
    channels: tuple[ChannelSpec, ...]
    training_target_channel: str
    audit_only_channels: tuple[str, ...]

    def channel(self, name: str) -> ChannelSpec | None:
        """Return the named channel spec, or None when absent.

        Args:
            name: Channel name to look up.

        Returns:
            (ChannelSpec | None) The spec, or None.
        """
        return next((channel for channel in self.channels if channel.name == name), None)


def load_schema(path: Path = CONTRACT_PATH) -> ActionObservationSchema:
    """Parse the frozen schema from the contract YAML.

    Args:
        path: Location of `contracts/action_observation.yaml`.

    Returns:
        (ActionObservationSchema) The parsed schema, unvalidated. Call
        `validate_schema` to enforce the structural invariants.
    """
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_schema(document)


def parse_schema(document: dict[str, Any]) -> ActionObservationSchema:
    """Build a schema object from an already-loaded contract document.

    Kept separate from `load_schema` so the invariant checks can run over an
    in-memory fixture without a temporary file.

    Args:
        document: Parsed contract mapping with a `channels` list.

    Returns:
        (ActionObservationSchema) The parsed schema.
    """
    channels: list[ChannelSpec] = []
    for raw in document.get("channels", []) or []:
        dim = raw.get("dim")
        channels.append(
            ChannelSpec(
                name=str(raw.get("name", "")),
                role=str(raw.get("role", "")),
                unit=str(raw.get("unit", "")),
                dim=int(dim) if dim is not None else None,
                position_only=bool(raw.get("position_only", False)),
                training_target=bool(raw.get("training_target", False)),
                fields=tuple(raw.get("fields", []) or []),
            )
        )
    return ActionObservationSchema(
        contract=str(document.get("contract", "")),
        frozen_digest=str(document.get("frozen_digest", "")),
        channels=tuple(channels),
        training_target_channel=str(document.get("training_target_channel", "")),
        audit_only_channels=tuple(document.get("audit_only_channels", []) or []),
    )


def validate_schema(schema: ActionObservationSchema) -> tuple[str, ...]:
    """Return every way the frozen schema violates its structural invariants.

    The checks are WP-0A-02 acceptance, structural half:

    - All six SPINE §6 channels are declared exactly once (acceptance ①).
    - Both action targets are position-only in `Deg` — no torque unit on an action
      target (acceptance ③, declaration side).
    - Exactly one channel is the training target, it is position-only, and it is
      the one named in `training_target_channel` (audit-vs-training separation).
    - The audit-only channels declare `training_target: false` and are not the
      training target (00 §8.3).
    - The observation channel is 48-dim bimanual (acceptance ⑦, declaration side).
    - The MIT audit fields carry their CAN-boundary units (12 §2.7).

    Args:
        schema: The parsed schema.

    Returns:
        (tuple[str, ...]) One message per violation; empty when the schema holds.
    """
    violations: list[str] = []

    names = [channel.name for channel in schema.channels]
    for required in REQUIRED_CHANNELS:
        if names.count(required) == 0:
            violations.append(f"channel '{required}' is not declared")
        elif names.count(required) > 1:
            violations.append(f"channel '{required}' is declared more than once")
    for name in names:
        if name not in REQUIRED_CHANNELS:
            violations.append(f"channel '{name}' is not part of the frozen six")

    violations.extend(_validate_action_targets(schema))
    violations.extend(_validate_training_target(schema))
    violations.extend(_validate_audit_channels(schema))
    violations.extend(_validate_observation(schema))
    violations.extend(_validate_mit_fields(schema))

    return tuple(violations)


def _validate_action_targets(schema: ActionObservationSchema) -> list[str]:
    """Check both action-target channels are position-only degrees, correct width."""
    violations: list[str] = []
    for name in ACTION_TARGET_CHANNELS:
        channel = schema.channel(name)
        if channel is None:
            continue
        if not channel.position_only:
            violations.append(f"action target '{name}' must be position_only")
        if channel.unit != _POSITION_UNIT:
            violations.append(
                f"action target '{name}' must carry unit '{_POSITION_UNIT}', not '{channel.unit}'"
            )
        if channel.dim != BIMANUAL_ACTION_DIM:
            violations.append(
                f"action target '{name}' must be {BIMANUAL_ACTION_DIM}-dim, got {channel.dim}"
            )
    return violations


def _validate_training_target(schema: ActionObservationSchema) -> list[str]:
    """Check exactly one position-only training target, and it is the named one."""
    violations: list[str] = []
    targets = [channel.name for channel in schema.channels if channel.training_target]
    if targets != [TRAINING_TARGET_CHANNEL]:
        violations.append(
            f"training target must be exactly ['{TRAINING_TARGET_CHANNEL}'], got {targets}"
        )
    if schema.training_target_channel != TRAINING_TARGET_CHANNEL:
        violations.append(
            f"training_target_channel must be '{TRAINING_TARGET_CHANNEL}', "
            f"got '{schema.training_target_channel}'"
        )
    target = schema.channel(TRAINING_TARGET_CHANNEL)
    if target is not None and not target.position_only:
        violations.append(f"training target '{TRAINING_TARGET_CHANNEL}' must be position_only")
    return violations


def _validate_audit_channels(schema: ActionObservationSchema) -> list[str]:
    """Check the audit-only channels can never be a training target (00 §8.3)."""
    violations: list[str] = []
    declared = set(schema.audit_only_channels)
    for name in AUDIT_ONLY_CHANNELS:
        if name not in declared:
            violations.append(f"audit-only channel '{name}' is not declared audit-only")
        channel = schema.channel(name)
        if channel is not None and channel.training_target:
            violations.append(f"audit-only channel '{name}' must not be a training target")
        if name == schema.training_target_channel:
            violations.append(f"audit-only channel '{name}' must not be the training target")
    return violations


def _validate_observation(schema: ActionObservationSchema) -> list[str]:
    """Check the observation channel is the full 48-dim bimanual vector."""
    observation = schema.channel("rawObservation")
    if observation is not None and observation.dim != BIMANUAL_OBSERVATION_DIM:
        return [
            f"rawObservation must be {BIMANUAL_OBSERVATION_DIM}-dim bimanual, got {observation.dim}"
        ]
    return []


def _validate_mit_fields(schema: ActionObservationSchema) -> list[str]:
    """Check the MIT audit fields declare their CAN-boundary units (12 §2.7)."""
    violations: list[str] = []
    mit = schema.channel("executedMitCommand")
    if mit is None:
        return violations
    declared = {str(field.get("name")): str(field.get("unit", "")) for field in mit.fields}
    for field_name, unit in MIT_FIELD_UNITS.items():
        if declared.get(field_name) != unit:
            violations.append(
                f"executedMitCommand field '{field_name}' must carry unit '{unit}', "
                f"got '{declared.get(field_name)}'"
            )
    return violations


def validate_frame(*, has_requested: bool, has_accepted: bool) -> tuple[str, ...]:
    """Reject a recorded frame that keeps one action channel without the other.

    Acceptance ②: recording only the post-clamp accepted action erases the
    request, and recording only the request hides what was executed. Both must be
    present together, or neither.

    Args:
        has_requested: Whether the frame carries `requestedPositionAction`.
        has_accepted: Whether the frame carries `acceptedPositionAction`.

    Returns:
        (tuple[str, ...]) One message when exactly one action channel is present;
        empty when both are present or both absent.
    """
    if has_requested and not has_accepted:
        return (
            "frame records requestedPositionAction without acceptedPositionAction; "
            "the executed action is unknown",
        )
    if has_accepted and not has_requested:
        return (
            "frame records acceptedPositionAction without requestedPositionAction; "
            "intervention and clamp saturation become undebuggable (00 §8.3)",
        )
    return ()


def is_audit_only(schema: ActionObservationSchema, channel_name: str) -> bool:
    """Report whether a channel is audit-only and thus forbidden as a training target.

    Args:
        schema: The parsed schema.
        channel_name: Channel to test.

    Returns:
        (bool) True when the channel may never be a training target.
    """
    return channel_name in schema.audit_only_channels
