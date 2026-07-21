"""WP-BOOT-01 acceptance criteria, as executable checks.

Criterion numbering follows `docs/plan/02a-작업패키지-Wave-minus1-to-1.md` §-2.3,
row `WP-BOOT-01`.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from registry.ingest.build import build
from registry.ingest.catalog import parse_all as parse_catalogs
from registry.ingest.spec import parse_all as parse_spec

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = REPO_ROOT / "docs" / "plan"
SPEC_DIR = REPO_ROOT / "docs" / "spec"
SCHEMA_PATH = REPO_ROOT / "registry" / "schema" / "traceability.schema.json"
REGISTRY_PATH = REPO_ROOT / "registry" / "traceability.yaml"

ISSUED_PACKAGE_COUNT = 177
SPINE_REF = "docs/plan/00-실행계획-개요.md@9b521ad"


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """Return the registry JSON Schema."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """Return a freshly seeded registry document."""
    built, _ = build(PLAN_DIR, SPEC_DIR, SPINE_REF)
    return built


@pytest.fixture(scope="module")
def valid_entry(document: dict[str, Any]) -> dict[str, Any]:
    """Return one record that already validates, for mutation fixtures."""
    return copy.deepcopy(
        next(entry for entry in document["entries"] if entry["wp"].startswith("WP-"))
    )


def _errors(schema: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    """Validate a single record inside a minimal document wrapper."""
    wrapper = {"version": 1, "spine_ref": SPINE_REF, "entries": [entry]}
    return [error.message for error in Draft202012Validator(schema).iter_errors(wrapper)]


# Criterion 1 — every issued work package has a record, difference zero in both directions.


def test_every_issued_package_is_registered(document: dict[str, Any]) -> None:
    """No issued package is missing from the registry."""
    issued = {entry.wp_id for entry in parse_catalogs(PLAN_DIR)}
    assert len(issued) == ISSUED_PACKAGE_COUNT
    registered = {entry["wp"] for entry in document["entries"]} - {"DEFERRED", "OUT"}
    assert not issued - registered


def test_registry_invents_no_package(document: dict[str, Any]) -> None:
    """The registry registers ids; it does not issue them."""
    issued = {entry.wp_id for entry in parse_catalogs(PLAN_DIR)}
    registered = {entry["wp"] for entry in document["entries"]} - {"DEFERRED", "OUT"}
    assert not registered - issued


# Criterion 2 and 8 — required axes, and violation fixtures the schema must reject.


@pytest.mark.parametrize(
    "axis",
    ["req", "spec_ref", "priority", "tag", "wp", "gate", "negative_branch", "stale_on", "env_hash"],
)
def test_missing_axis_is_rejected(
    schema: dict[str, Any], valid_entry: dict[str, Any], axis: str
) -> None:
    """A record missing a required axis fails schema validation."""
    broken = copy.deepcopy(valid_entry)
    broken.pop(axis)
    assert _errors(schema, broken)


@pytest.mark.fixture_corpus
@pytest.mark.parametrize(
    ("label", "mutation"),
    [
        ("bare PG-RT-001 in the gate axis", {"gate": ["PG-RT-001"]}),
        ("semver contract id", {"contract": {"consumes": ["CTR-ACT@1.2.0"], "produces": []}}),
        ("own mode outside the vocabulary", {"owns": [{"glob": "a", "mode": "WRITEABLE"}]}),
        ("priority outside M/S/C", {"priority": "—"}),
        ("tag outside the vocabulary", {"tag": "개정"}),
        ("workflow outside the shape vocabulary", {"workflow": "SHAPE-XX"}),
        ("wp id that is not an id", {"wp": "WP-NOPE-99x9"}),
    ],
)
def test_violation_fixtures_are_rejected(
    schema: dict[str, Any], valid_entry: dict[str, Any], label: str, mutation: dict[str, Any]
) -> None:
    """Each named violation fails validation."""
    broken = copy.deepcopy(valid_entry)
    broken.update(mutation)
    assert _errors(schema, broken), f"{label} was accepted"


def test_scalar_shape_and_phases_are_mutually_exclusive(
    schema: dict[str, Any], valid_entry: dict[str, Any]
) -> None:
    """Two encodings of the same fact must not coexist."""
    broken = copy.deepcopy(valid_entry)
    broken["workflow"] = "SHAPE-CF"
    broken["exec_class"] = "AI-offline"
    broken["phases"] = [
        {
            "workflow": "SHAPE-IM",
            "exec_class": "AI-offline",
            "owns": [],
            "cancel_policy": "finish-step",
        },
        {
            "workflow": "SHAPE-HG",
            "exec_class": "Human-judgment",
            "owns": [],
            "cancel_policy": "latch-to-hold",
        },
    ]
    assert _errors(schema, broken)


# Criterion 3 and 5 — gate axis references, and the PG-RT-001 split.


def test_split_gate_ids_are_accepted(schema: dict[str, Any], valid_entry: dict[str, Any]) -> None:
    """`PG-RT-001a` is a gate id even though bare `PG-RT-001` is not.

    Over-blocking here would be as wrong as under-blocking: the ban is on the
    unsplit id, not on the family.
    """
    entry = copy.deepcopy(valid_entry)
    entry["gate"] = ["PG-RT-001a"]
    entry["negative_branch"] = [
        {"gate": "PG-RT-001a", "on": "SUPERSEDED", "action": "b supersedes a"}
    ]
    assert not _errors(schema, entry)


def test_no_record_carries_a_bare_split_gate(document: dict[str, Any]) -> None:
    """Criterion 5: the gate axis holds zero bare `PG-RT-001` values."""
    assert not [
        entry["req"] for entry in document["entries"] if "PG-RT-001" in entry.get("gate", [])
    ]


def test_no_record_carries_the_sealed_measurement_id(document: dict[str, Any]) -> None:
    """Criterion 6: `M-8` never appears as a gate-axis value.

    The seal is on the field value, not on prose — a checker that greps the
    documents fails on the sentence describing the seal.
    """
    sealed = re.compile(r"^M-8\b")
    assert not [
        entry["req"]
        for entry in document["entries"]
        for gate in entry.get("gate", [])
        if sealed.match(gate)
    ]


# Criterion 4 — a gate with no designed failure path is not a gate.


def test_every_gate_has_a_negative_branch(document: dict[str, Any]) -> None:
    """Criterion 4: each gate carries at least one non-PASS branch."""
    for entry in document["entries"]:
        declared = {branch["gate"] for branch in entry.get("negative_branch", [])}
        assert not set(entry.get("gate", [])) - declared, entry["req"]


def test_acceptance_check_branches_are_binary(document: dict[str, Any]) -> None:
    """A `CG-*` is PASS/FAIL; the five-state machine belongs to `PG-*` alone.

    Anything else lets a package lower its own acceptance bar and declare
    itself passed, with no checker able to see it.
    """
    for entry in document["entries"]:
        for branch in entry.get("negative_branch", []):
            if branch["gate"].startswith("CG-"):
                assert branch["on"] == "FAIL", entry["req"]


# Criterion 9 — the band applies its own rules to itself.


def test_boot_band_registers_itself(document: dict[str, Any]) -> None:
    """Criterion 9: the five BOOT packages hold records of their own."""
    boot = {entry["wp"] for entry in document["entries"] if entry["wp"].startswith("WP-BOOT-")}
    assert boot == {f"WP-BOOT-{index:02d}" for index in range(1, 6)}


def test_plan_axis_records_carry_no_invented_requirement(document: dict[str, Any]) -> None:
    """Machinery packages use `PLAN-*`; inventing an `FR-*` would violate CI-01b."""
    declared = {requirement.req_id for requirement in parse_spec(SPEC_DIR)}
    for entry in document["entries"]:
        if entry["req"].startswith("PLAN-"):
            continue
        assert entry["req"] in declared, entry["req"]


# stale_on has two provenances that must stay distinct: contract major bumps are
# derived from the consumes axis, gate re-derivation triggers are declared by the
# author. Deriving the second would blind CI-11c; not deriving the first would make
# every consumer of a bumped contract silently survive.


def test_contract_bump_trigger_is_derived_from_consumes(document: dict[str, Any]) -> None:
    """A consumer of `CTR-PRIM@v1` goes stale on its major bump (`06` §4.3)."""
    record = next(entry for entry in document["entries"] if entry["wp"] == "WP-3A-01")
    assert "CTR-PRIM@v1" in record["contract"]["consumes"]
    assert "CTR-PRIM:MAJOR_BUMP" in record["stale_on"]


def test_provisional_re_derivation_trigger_is_declared(document: dict[str, Any]) -> None:
    """Consumers of the provisional gate declare the final gate's trigger (CI-11c).

    The trigger is read from the catalogue `재도출 =` clause, never derived from the
    gate axis, so a package that drops the declaration re-fails CI-11c.
    """
    for wp_id in ("WP-1-04", "WP-1-05", "WP-1-06"):
        record = next(entry for entry in document["entries"] if entry["wp"] == wp_id)
        assert "PG-RT-001b:PASS" in record["stale_on"], wp_id


# Determinism, and the committed artefact matching what the seeder produces.


def test_seeding_is_deterministic() -> None:
    """The same corpus produces the same registry, byte for byte."""
    first, _ = build(PLAN_DIR, SPEC_DIR, SPINE_REF)
    second, _ = build(PLAN_DIR, SPEC_DIR, SPINE_REF)
    assert yaml.safe_dump(first, allow_unicode=True) == yaml.safe_dump(second, allow_unicode=True)


def test_committed_registry_validates(schema: dict[str, Any]) -> None:
    """The registry on disk validates against its own schema."""
    on_disk = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(on_disk))


def test_committed_registry_is_sorted_by_requirement() -> None:
    """`06` §2.1 makes requirement order a property of the file, not a convention."""
    on_disk = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    requirements = [entry["req"] for entry in on_disk["entries"]]
    assert requirements == sorted(requirements)
