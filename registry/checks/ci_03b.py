"""CI-03b — error-code prefix exclusivity: one issuing area per `OA-<domain>-*`.

`06` §3.2 allows `contracts/errors/oa_codes.yaml` to be `SHARED_APPEND` because
fifteen area packages all issue codes; the offsetting rule is this one, which
holds each domain prefix to a single issuing area and forbids number reuse inside
a domain. The specification has already been injured by exactly this failure —
`14` §2.10 and `08` double-assigned `OA-DAT-003/004/005`, forcing a renumber.

Scope limit, stated rather than hidden. `06` §5 asks for two judgements: duplicate
numbers within a domain, and whether the issuing package "is that area's work
package". The first is mechanically decidable from the code registry. The second
needs a canonical domain-to-band mapping, and no planning document defines one, so
this rule enforces the decidable halves — number reuse, and one domain being
issued by two different areas — and does not guess at the mapping.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import yaml

from registry.checks.corpus import Corpus
from registry.checks.model import RuleResult, fail

RULE_ID = "CI-03b"
TITLE = "error-code prefix exclusivity"

OA_CODE_REGISTRY = "contracts/errors/oa_codes.yaml"

OA_CODE = re.compile(r"^OA-(?P<domain>[A-Z]+)-(?P<number>\d{3})$")


def _load_codes(corpus: Corpus) -> list[dict[str, Any]]:
    """Read the `OA-*` code registry when it exists.

    Args:
        corpus: The corpus under test.

    Returns:
        (list[dict[str, Any]]) Code rows, empty when the registry is absent.
    """
    path = corpus.root / OA_CODE_REGISTRY
    if not path.is_file():
        return []
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = loaded.get("codes", []) if isinstance(loaded, dict) else loaded
    return [row for row in (rows or []) if isinstance(row, dict)]


def run(corpus: Corpus) -> RuleResult:
    """Report reused code numbers and domains issued by more than one area.

    Args:
        corpus: The corpus under test.

    Returns:
        (RuleResult) One finding per duplicate number or split domain.
    """
    rows = _load_codes(corpus)
    findings = []

    seen: dict[str, list[str]] = defaultdict(list)
    domain_issuers: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        code = str(row.get("code", ""))
        match = OA_CODE.match(code)
        if not match:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=code or "(unnamed)",
                    path=OA_CODE_REGISTRY,
                    reason="error code does not follow the OA-<domain>-<3 digits> form",
                    expected="OA-<DOMAIN>-nnn",
                    actual=code or "(empty code field)",
                )
            )
            continue
        issuer = str(row.get("wp", "")) or "(unattributed)"
        seen[code].append(issuer)
        domain_issuers[match.group("domain")].add(issuer)

    for code, issuers in sorted(seen.items()):
        if len(issuers) > 1:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=code,
                    path=OA_CODE_REGISTRY,
                    reason=(
                        "error code number is issued more than once; SHARED_APPEND "
                        "permits adding rows, never reusing a number"
                    ),
                    expected="one row per error code",
                    actual=f"{len(issuers)} rows, issued by {', '.join(sorted(issuers))}",
                )
            )

    for domain, areas in sorted(domain_issuers.items()):
        if len(areas) > 1:
            findings.append(
                fail(
                    rule_id=RULE_ID,
                    req_or_wp=f"OA-{domain}-*",
                    path=OA_CODE_REGISTRY,
                    reason="one error-code domain prefix is issued by more than one work package",
                    expected="a single issuing work package per domain prefix",
                    actual=f"issued by {', '.join(sorted(areas))}",
                )
            )

    notes: tuple[str, ...] = ()
    if not rows:
        notes = (
            f"{OA_CODE_REGISTRY} does not exist yet, so this rule examined no codes. "
            "Detection is proven by fixture, not by this run.",
        )

    return RuleResult(
        rule_id=RULE_ID,
        findings=tuple(findings),
        sites=len(rows),
        vacuous=not rows,
        notes=notes,
    )
