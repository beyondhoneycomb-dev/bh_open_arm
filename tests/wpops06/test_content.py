"""Content acceptance: coverage, fields, severity, uniqueness, domains, nibble map.

Acceptance ①②③④⑤⑧⑨. Each check passes on the real frozen registry and fires on
a one-field perturbation, so no checker is green while catching nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from contracts.errors.checkers import (
    Finding,
    all_findings,
    check_coverage,
    check_domains,
    check_field_completeness,
    check_nibble_bijection,
    check_severity,
    check_uniqueness,
)
from contracts.errors.registry import REGISTRY, Registry

Mutator = Callable[[Callable[[dict[str, Any]], None]], Registry]


def test_real_registry_is_clean(required_codes: set[str]) -> None:
    """The frozen registry passes every content check (acceptance ①②③④⑤⑨)."""
    assert all_findings(REGISTRY, required_codes) == []


def test_covers_every_canon_and_sys_code(required_codes: set[str]) -> None:
    """0 spec-present-but-registry-absent codes (acceptance ①, ⑧)."""
    assert check_coverage(REGISTRY, required_codes) == []
    for number in range(1, 12):
        assert f"OA-SYS-{number:03d}" in REGISTRY.codes


def test_missing_code_fails_coverage() -> None:
    """A spec code absent from the registry is reported (acceptance ①)."""
    findings = check_coverage(REGISTRY, {"OA-CAN-001", "OA-CAN-999"})
    assert Finding("coverage", "OA-CAN-999", "spec-present but registry-absent") in findings


def test_partial_row_fails_fields(mutate: Mutator) -> None:
    """A code missing a field is caught (acceptance ②)."""

    def drop_recovery_hint(document: dict[str, Any]) -> None:
        del document["codes"][0]["recovery_hint"]

    findings = check_field_completeness(mutate(drop_recovery_hint))
    assert any(f.check == "fields" and "recovery_hint" in f.reason for f in findings)


def test_out_of_range_severity_fails(mutate: Mutator) -> None:
    """A severity outside the four levels is rejected (acceptance ③)."""

    def bad_severity(document: dict[str, Any]) -> None:
        document["codes"][0]["severity"] = 7

    findings = check_severity(mutate(bad_severity))
    assert any(f.check == "severity" and "outside" in f.reason for f in findings)


def test_widened_severity_map_fails(mutate: Mutator) -> None:
    """Declaring a fifth severity level is rejected (acceptance ③)."""

    def widen(document: dict[str, Any]) -> None:
        document["severity_levels"]["FATAL"] = 4

    findings = check_severity(mutate(widen))
    assert any(f.subject == "severity_levels" for f in findings)


def test_duplicate_code_fails(mutate: Mutator) -> None:
    """The same code defined twice is rejected (acceptance ⑤)."""

    def duplicate(document: dict[str, Any]) -> None:
        document["codes"].append(dict(document["codes"][0]))

    findings = check_uniqueness(mutate(duplicate))
    assert any(f.check == "uniqueness" and "2 times" in f.reason for f in findings)


def test_code_outside_domains_fails(mutate: Mutator) -> None:
    """A code in a domain outside the closed set is rejected (acceptance ⑨)."""

    def foreign_domain(document: dict[str, Any]) -> None:
        row = dict(document["codes"][0])
        row["code"] = "OA-XXX-001"
        document["codes"].append(row)

    findings = check_domains(mutate(foreign_domain))
    assert any(f.subject == "OA-XXX-001" and "closed set" in f.reason for f in findings)


def test_malformed_code_fails(mutate: Mutator) -> None:
    """A code not matching the grammar is rejected (acceptance ⑨)."""

    def malformed(document: dict[str, Any]) -> None:
        document["codes"][0]["code"] = "OACAN3"

    findings = check_domains(mutate(malformed))
    assert any("does not match" in f.reason for f in findings)


def test_nibble_bijection_holds() -> None:
    """The seven Damiao error nibbles map 1:1 to distinct OA-MOT codes (acceptance ④)."""
    assert check_nibble_bijection(REGISTRY) == []


def test_missing_nibble_fails(mutate: Mutator) -> None:
    """Dropping an error nibble breaks the bijection (acceptance ④)."""

    def drop_overload(document: dict[str, Any]) -> None:
        document["damiao_err_nibble_map"] = [
            row for row in document["damiao_err_nibble_map"] if row["nibble"] != "E"
        ]

    findings = check_nibble_bijection(mutate(drop_overload))
    assert any(f.subject == "E" and "not mapped" in f.reason for f in findings)


def test_duplicate_nibble_target_fails(mutate: Mutator) -> None:
    """Two nibbles mapping to one code breaks the bijection (acceptance ④)."""

    def collide(document: dict[str, Any]) -> None:
        for row in document["damiao_err_nibble_map"]:
            if row["nibble"] == "9":
                row["code"] = "OA-MOT-008"

    findings = check_nibble_bijection(mutate(collide))
    assert any("mapped by two nibbles" in f.reason for f in findings)
