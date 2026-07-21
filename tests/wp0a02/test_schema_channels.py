"""The frozen CTR-ACT@v1 schema declares all six channels with a version (WP-0A-02).

Acceptance ①: the six SPINE §6 channels are each defined once and the contract
carries a version tag. The shipped `contracts/action_observation.yaml` must
validate with no structural violations, and a fixture dropping or duplicating a
channel must be reported.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml

from contracts.action import (
    CONTRACT_ID,
    REQUIRED_CHANNELS,
    load_schema,
    parse_schema,
    validate_schema,
)
from contracts.action.schema import CONTRACT_PATH


def _document() -> dict[str, Any]:
    """Return the shipped contract document parsed from YAML."""
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_carries_version_tag() -> None:
    """The frozen schema declares its contract id and generation."""
    assert load_schema().contract == CONTRACT_ID


def test_all_six_channels_declared_once() -> None:
    """Exactly the six SPINE §6 channels are present, none extra, none repeated."""
    schema = load_schema()
    names = [channel.name for channel in schema.channels]
    assert names == list(REQUIRED_CHANNELS)


def test_shipped_schema_validates_clean() -> None:
    """The shipped contract has no structural violations."""
    assert validate_schema(load_schema()) == ()


def test_missing_channel_is_reported() -> None:
    """Dropping a required channel is a validation violation (acceptance ①)."""
    document = _document()
    document["channels"] = [c for c in document["channels"] if c["name"] != "executedMitCommand"]
    violations = validate_schema(parse_schema(document))
    assert any("executedMitCommand" in message for message in violations)


def test_duplicate_channel_is_reported() -> None:
    """Declaring a channel twice is a validation violation."""
    document = _document()
    duplicate = copy.deepcopy(document["channels"][0])
    document["channels"].append(duplicate)
    violations = validate_schema(parse_schema(document))
    assert any("more than once" in message for message in violations)


def test_unknown_channel_is_reported() -> None:
    """A channel outside the frozen six is rejected."""
    document = _document()
    document["channels"].append({"name": "gravityTorqueTarget", "role": "action_accepted"})
    violations = validate_schema(parse_schema(document))
    assert any("not part of the frozen six" in message for message in violations)
