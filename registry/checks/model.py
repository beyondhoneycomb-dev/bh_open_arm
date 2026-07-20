"""Report record and check-module contract shared by every CI checker.

The report shape is fixed by `06` §5: `{rule_id, severity, req_or_wp, path,
reason}`. That section also rules that a record carrying fewer than four
populated fields means *the checker itself* failed, so `Finding` enforces the
floor at construction time rather than at print time — a malformed record must
not survive long enough to be counted as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

SEVERITY_FAIL = "FAIL"

# `06` §5 rules that every check is build-failing and that no warning level exists,
# because a warning is ignored and an ignored check is not a check. One severity.
VALID_SEVERITIES = frozenset({SEVERITY_FAIL})

MIN_POPULATED_FIELDS = 4

_CANONICAL_FIELDS = ("rule_id", "severity", "req_or_wp", "path", "reason")


class CheckerContractError(RuntimeError):
    """Raised when a checker emits a record that violates the report contract.

    This is deliberately not a `Finding`. A checker that cannot describe its own
    violation has failed as a checker, and `06` §5 makes that a distinct failure
    from the rule being violated.
    """


@dataclass(frozen=True)
class Finding:
    """One rule violation, in the fixed machine-readable shape of `06` §5.

    `expected` and `actual` are additive: `02a` §−2.3 states the report format as
    `{ci_id, violation location, expected, actual}` while `06` §5 states it as the
    five canonical fields. The two documents disagree, so a record carries both — the
    five canonical fields are the contract, and the two extras satisfy `02a`
    acceptance ⑩ without weakening it.

    Attributes:
        rule_id: The `CI-*` identifier that produced this record.
        severity: Always `FAIL`; there is no warning level.
        req_or_wp: The `req` or `WP-*` the violation is attributed to.
        path: Where the violation lives, as `<file>` or `<file>:<line>`.
        reason: Why this is a violation, in terms a reader can act on.
        expected: What the rule requires, when it can be stated concisely.
        actual: What was found instead.
    """

    rule_id: str
    severity: str
    req_or_wp: str
    path: str
    reason: str
    expected: str = ""
    actual: str = ""

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise CheckerContractError(
                f"{self.rule_id}: severity {self.severity!r} is not one of "
                f"{sorted(VALID_SEVERITIES)}"
            )
        populated = sum(1 for name in _CANONICAL_FIELDS if getattr(self, name).strip())
        if populated < MIN_POPULATED_FIELDS:
            raise CheckerContractError(
                f"{self.rule_id}: report record populates {populated} of "
                f"{len(_CANONICAL_FIELDS)} canonical fields, below the floor of "
                f"{MIN_POPULATED_FIELDS} required by 06 §5"
            )

    def as_dict(self) -> dict[str, str]:
        """Render the record as the canonical five fields plus the two extras.

        Returns:
            (dict[str, str]) Field name to value, canonical fields first.
        """
        record = {name: getattr(self, name) for name in _CANONICAL_FIELDS}
        if self.expected:
            record["expected"] = self.expected
        if self.actual:
            record["actual"] = self.actual
        return record

    def as_line(self) -> str:
        """Render the record as one terminal line.

        Returns:
            (str) Single-line human-readable form.
        """
        return f"{self.rule_id} {self.severity} {self.req_or_wp} {self.path} :: {self.reason}"


def fail(
    rule_id: str,
    req_or_wp: str,
    path: str,
    reason: str,
    expected: str = "",
    actual: str = "",
) -> Finding:
    """Build a build-failing record without repeating the severity at every site.

    Args:
        rule_id: The `CI-*` identifier reporting the violation.
        req_or_wp: The `req` or `WP-*` the violation is attributed to.
        path: Where the violation lives.
        reason: Why this is a violation.
        expected: What the rule requires.
        actual: What was found instead.

    Returns:
        (Finding) A validated record with severity `FAIL`.
    """
    return Finding(
        rule_id=rule_id,
        severity=SEVERITY_FAIL,
        req_or_wp=req_or_wp,
        path=path,
        reason=reason,
        expected=expected,
        actual=actual,
    )


@dataclass(frozen=True)
class RuleResult:
    """Outcome of running one rule over one corpus.

    `findings` being empty is not by itself evidence the rule holds — see
    `vacuous`, which records that the rule found no *sites* to judge. `06` §5
    treats an unrun checker as unproven, and a checker with nothing to look at is
    the same condition with a friendlier face.

    Attributes:
        rule_id: The `CI-*` identifier.
        findings: Violations, in discovery order.
        sites: Number of declaration sites the rule actually examined.
        vacuous: True when `sites` is zero, so green means "nothing to judge".
        notes: Diagnostics that are not violations — a rule uses this to surface a
            disagreement between its literal wording and its implementable form
            instead of silently resolving it in either direction.
    """

    rule_id: str
    findings: tuple[Finding, ...]
    sites: int
    vacuous: bool = field(default=False)
    notes: tuple[str, ...] = field(default=())

    @property
    def passed(self) -> bool:
        """Report whether the rule produced no violations.

        Returns:
            (bool) True when there are no findings.
        """
        return not self.findings


class CheckModule(Protocol):
    """Structural contract every `registry/checks/ci_*.py` module satisfies."""

    RULE_ID: str
    TITLE: str

    def run(self, corpus: object) -> RuleResult:  # pragma: no cover - protocol only
        """Evaluate the rule over a corpus."""
        ...
