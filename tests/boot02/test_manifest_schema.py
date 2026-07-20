"""Manifest schema rejection rules.

Acceptance criteria `02a` §−2.3 `WP-BOOT-02` ⑥ ⑦ ⑧ ⑨ plus the scalar/`phases[]`
mutual exclusion and the `contract_refs[]` derivation rule from the contract
cell. Every rule is exercised from both sides: a fixture that must fail and a
fixture that must stay green, because a schema that rejects nothing is
indistinguishable from a schema that is never consulted.
"""

from __future__ import annotations

from typing import Any

import pytest

from registry.generate.manifests import schema_errors


def test_pass_fixture_single_stage(single_stage_manifest: dict[str, Any]) -> None:
    """A well-formed single-stage manifest validates."""
    assert schema_errors(single_stage_manifest) == []


def test_pass_fixture_multi_stage(multi_stage_manifest: dict[str, Any]) -> None:
    """A well-formed multi-stage manifest validates."""
    assert schema_errors(multi_stage_manifest) == []


# ⑥ exec_class / workflow value spaces are closed, one token per scalar cell.


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow", "SHAPE-XX"),
        ("workflow", "SHAPE-SEQ"),
        ("exec_class", "AI-hybrid"),
        ("exec_class", "Human-in-the-loop"),
    ],
)
def test_third_vocabulary_rejected(
    single_stage_manifest: dict[str, Any], field: str, value: str
) -> None:
    """A shape or class token outside the closed value space is rejected."""
    single_stage_manifest[field] = value
    assert schema_errors(single_stage_manifest) != []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow", "SHAPE-IM + SHAPE-HG"),
        ("workflow", "SHAPE-IM -> SHAPE-MS"),
        ("exec_class", "AI-offline + AI-on-HW"),
        ("exec_class", "AI-offline -> AI-on-HW"),
    ],
)
def test_two_tokens_in_one_scalar_rejected(
    single_stage_manifest: dict[str, Any], field: str, value: str
) -> None:
    """Two tokens in a scalar cell are rejected; multi-stage belongs in phases[]."""
    single_stage_manifest[field] = value
    assert schema_errors(single_stage_manifest) != []


# Scalars and phases[] are mutually exclusive.


def test_scalars_and_phases_together_rejected(
    single_stage_manifest: dict[str, Any], multi_stage_manifest: dict[str, Any]
) -> None:
    """Declaring both the scalars and phases[] is rejected."""
    single_stage_manifest["phases"] = multi_stage_manifest["phases"]
    assert schema_errors(single_stage_manifest) != []


def test_neither_scalars_nor_phases_rejected(single_stage_manifest: dict[str, Any]) -> None:
    """Declaring neither the scalars nor phases[] is rejected."""
    del single_stage_manifest["workflow"]
    del single_stage_manifest["exec_class"]
    assert schema_errors(single_stage_manifest) != []


# ⑦ normalization_hash and env_hash must be declared, null included.


@pytest.mark.parametrize("field", ["normalization_hash", "env_hash"])
def test_undeclared_hash_slot_rejected(single_stage_manifest: dict[str, Any], field: str) -> None:
    """Omitting a hash slot is rejected even though a later wave fills it."""
    del single_stage_manifest[field]
    assert schema_errors(single_stage_manifest) != []


@pytest.mark.parametrize("field", ["normalization_hash", "env_hash"])
def test_declared_hash_slot_accepts_null_and_digest(
    single_stage_manifest: dict[str, Any], field: str
) -> None:
    """A declared slot holds either null or a sha256 digest."""
    single_stage_manifest[field] = "sha256:" + "0" * 64
    assert schema_errors(single_stage_manifest) == []


@pytest.mark.parametrize("field", ["normalization_hash", "env_hash"])
def test_malformed_hash_rejected(single_stage_manifest: dict[str, Any], field: str) -> None:
    """A declared slot does not accept an arbitrary string."""
    single_stage_manifest[field] = "pending"
    assert schema_errors(single_stage_manifest) != []


# ⑧ gate-bearing fields never carry a bare PG-RT-001 or an M-8.


@pytest.mark.parametrize("field", ["gates", "exit_gates", "requires_gates"])
@pytest.mark.parametrize("gate", ["PG-RT-001", "M-8"])
def test_sealed_gate_id_rejected(
    single_stage_manifest: dict[str, Any], field: str, gate: str
) -> None:
    """A sealed gate id is rejected in every gate-bearing field."""
    single_stage_manifest[field] = [gate]
    assert schema_errors(single_stage_manifest) != []


@pytest.mark.parametrize("field", ["gates", "exit_gates", "requires_gates"])
def test_split_gate_ids_accepted(single_stage_manifest: dict[str, Any], field: str) -> None:
    """The split PG-RT-001a / PG-RT-001b ids stay green in the same field."""
    single_stage_manifest[field] = ["PG-RT-001a", "PG-RT-001b", "CG-1-04a"]
    assert schema_errors(single_stage_manifest) == []


# ⑨ every stage carries exactly one shape token and a cancel policy.


def test_stage_without_cancel_policy_rejected(multi_stage_manifest: dict[str, Any]) -> None:
    """A stage missing cancel_policy is rejected."""
    del multi_stage_manifest["phases"][1]["cancel_policy"]
    assert schema_errors(multi_stage_manifest) != []


def test_stage_with_unknown_cancel_policy_rejected(multi_stage_manifest: dict[str, Any]) -> None:
    """A cancel policy outside {finish-step, latch-to-hold} is rejected."""
    multi_stage_manifest["phases"][1]["cancel_policy"] = "abort-immediately"
    assert schema_errors(multi_stage_manifest) != []


def test_stage_with_two_shape_tokens_rejected(multi_stage_manifest: dict[str, Any]) -> None:
    """Two shape tokens inside one stage are rejected."""
    multi_stage_manifest["phases"][0]["workflow"] = "SHAPE-IM + SHAPE-MS"
    assert schema_errors(multi_stage_manifest) != []


def test_stage_without_shape_token_rejected(multi_stage_manifest: dict[str, Any]) -> None:
    """A stage missing its shape token is rejected."""
    del multi_stage_manifest["phases"][0]["workflow"]
    assert schema_errors(multi_stage_manifest) != []


def test_single_element_phases_rejected(multi_stage_manifest: dict[str, Any]) -> None:
    """A one-stage phases[] is a single-stage package written the wrong way."""
    multi_stage_manifest["phases"] = multi_stage_manifest["phases"][:1]
    assert schema_errors(multi_stage_manifest) != []


def test_both_cancel_policies_accepted(multi_stage_manifest: dict[str, Any]) -> None:
    """Both cancel policies stay green on a well-formed stage list."""
    policies = {stage["cancel_policy"] for stage in multi_stage_manifest["phases"]}
    assert policies == {"finish-step", "latch-to-hold"}
    assert schema_errors(multi_stage_manifest) == []


# contract_refs[] is derived, never stored.


def test_stored_contract_refs_rejected(single_stage_manifest: dict[str, Any]) -> None:
    """A manifest may not store contract_refs[]; it is an index-side view."""
    single_stage_manifest["contract_refs"] = ["CTR-UNIT@v1"]
    assert schema_errors(single_stage_manifest) != []


def test_semver_contract_id_rejected(single_stage_manifest: dict[str, Any]) -> None:
    """Contract ids use the @v<n> generation token, never semver."""
    single_stage_manifest["consumes"] = ["CTR-ACT@1.2.0"]
    assert schema_errors(single_stage_manifest) != []
