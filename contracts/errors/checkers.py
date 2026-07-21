"""Standalone validators for the frozen registry, invoked by the WP-OPS-06 tests.

These are not CI rules (they add nothing to `06` §5) — they are the acceptance
checks a producer runs against its own artifact, the way WP-0B-07's write-symbol
static check is a test, not a gate. Each returns findings; empty means the corpus
under test is clean. The tests run every checker against the real registry (which
must be clean) and against a perturbed fixture (which must not be).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from contracts.errors.constants import (
    CODE_PATTERN,
    DAMIAO_ERROR_NIBBLES,
    DOMAINS,
    REQUIRED_FIELDS,
)
from contracts.errors.registry import Registry
from contracts.errors.severity import Severity, is_valid_severity


@dataclass(frozen=True)
class Finding:
    """One validation failure.

    Attributes:
        check: The validator that produced it.
        subject: The code, domain or symbol at fault.
        reason: What is wrong, in one line.
    """

    check: str
    subject: str
    reason: str


def check_field_completeness(registry: Registry) -> list[Finding]:
    """Every code row must carry all ten contract fields (acceptance ②)."""
    findings: list[Finding] = []
    for row in registry.raw_codes:
        if not isinstance(row, dict):
            findings.append(Finding("fields", str(row), "code row is not a mapping"))
            continue
        code = str(row.get("code", "(unnamed)"))
        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            findings.append(Finding("fields", code, f"missing field(s): {', '.join(missing)}"))
    return findings


def check_severity(registry: Registry) -> list[Finding]:
    """Severity must be one of the four fixed levels, per code and in the file map.

    Acceptance ③. Both the declared `severity_levels` map and each code's value
    are checked, so neither a widened enum nor an out-of-range code slips through.
    """
    findings: list[Finding] = []
    expected = {level.name: int(level) for level in Severity}
    if registry.severity_levels != expected:
        findings.append(
            Finding(
                "severity",
                "severity_levels",
                f"declared levels {registry.severity_levels} != fixed {expected}",
            )
        )
    for row in registry.raw_codes:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code", "(unnamed)"))
        if not is_valid_severity(row.get("severity")):
            findings.append(
                Finding("severity", code, f"severity {row.get('severity')!r} outside {expected}")
            )
    return findings


def check_uniqueness(registry: Registry) -> list[Finding]:
    """No code number may be defined twice (acceptance ⑤)."""
    counts = Counter(
        str(row.get("code", "")) for row in registry.raw_codes if isinstance(row, dict)
    )
    return [
        Finding("uniqueness", code, f"code defined {count} times")
        for code, count in sorted(counts.items())
        if code and count > 1
    ]


def check_domains(registry: Registry) -> list[Finding]:
    """Every code must match the grammar and sit in the closed domain set.

    Acceptance ⑨. A code outside the ten prefixes, or one that does not match
    `OA-<domain>-<3 chars>`, is rejected.
    """
    findings: list[Finding] = []
    domains = set(DOMAINS)
    for row in registry.raw_codes:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code", "(unnamed)"))
        match = CODE_PATTERN.match(code)
        if match is None:
            findings.append(Finding("domains", code, "does not match OA-<domain>-<3 chars>"))
            continue
        domain = f"OA-{match.group('domain')}"
        if domain not in domains:
            findings.append(Finding("domains", code, f"domain {domain} outside the closed set"))
    return findings


def check_nibble_bijection(registry: Registry) -> list[Finding]:
    """The seven Damiao error nibbles must map 1:1 to distinct OA-MOT codes.

    Acceptance ④: `8/9/A/B/C/D/E` all mapped, none missing, none duplicated, and
    every mapped code exists in the registry.
    """
    findings: list[Finding] = []
    by_nibble: dict[str, str] = {}
    code_counts: Counter[str] = Counter()
    for row in registry.nibble_map:
        if not isinstance(row, dict):
            continue
        nibble = str(row.get("nibble", "")).upper()
        code = str(row.get("code", ""))
        if nibble in by_nibble:
            findings.append(Finding("nibble", nibble, "nibble mapped more than once"))
        by_nibble[nibble] = code
        code_counts[code] += 1

    for nibble in DAMIAO_ERROR_NIBBLES:
        code = by_nibble.get(nibble)
        if code is None:
            findings.append(Finding("nibble", nibble, "error nibble is not mapped"))
            continue
        if code not in registry.codes:
            findings.append(Finding("nibble", nibble, f"maps to unregistered code {code}"))
        if code_counts[code] > 1:
            findings.append(Finding("nibble", nibble, f"code {code} is mapped by two nibbles"))
    return findings


def check_coverage(registry: Registry, required: set[str]) -> list[Finding]:
    """Every required code must be present in the registry (acceptance ①, ⑧, ⑫).

    Args:
        registry: The registry under test.
        required: Codes that must be present, read live from the spec.

    Returns:
        (list[Finding]) One finding per required code the registry lacks.
    """
    return [
        Finding("coverage", code, "spec-present but registry-absent")
        for code in sorted(required)
        if code not in registry.codes
    ]


def all_findings(registry: Registry, required: set[str]) -> list[Finding]:
    """Run every content validator and concatenate the findings.

    Args:
        registry: The registry under test.
        required: Codes that must be covered.

    Returns:
        (list[Finding]) All findings across the content checks.
    """
    findings: list[Finding] = []
    findings.extend(check_field_completeness(registry))
    findings.extend(check_severity(registry))
    findings.extend(check_uniqueness(registry))
    findings.extend(check_domains(registry))
    findings.extend(check_nibble_bijection(registry))
    findings.extend(check_coverage(registry, required))
    return findings
