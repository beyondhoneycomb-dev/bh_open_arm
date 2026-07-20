"""The violation vocabulary shared by every contract-side check.

Two report shapes are specified for a rule breach and neither contains the
other: `06` §5 (line 528) fixes `{rule_id, severity, req_or_wp, path, reason}`
while `02a` §-2.3 (`WP-BOOT-03` acceptance ⑩) fixes
`{ci_id, 위반 위치, 기대, 실측}`. This record carries the union so each consumer
projects the shape it owns; committing to one here would make the other
unrenderable without re-deriving information that was already discarded.
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_BLOCKING = "BLOCKING"


@dataclass(frozen=True)
class Violation:
    """One rule breach, located and quantified.

    Attributes:
        rule: Identifier of the broken rule (`CI-*` for a CI rule, `CR-*` for a
            contract freeze/thaw rule).
        severity: Fixed to `BLOCKING` for every contract rule — `06` §4.3
            leaves no advisory tier, a contract breach fails the build.
        location: Where the breach sits: a contract id, a work-package id, or a
            path into the index document.
        expected: What the rule requires at that location.
        actual: What was found there.
    """

    rule: str
    severity: str
    location: str
    expected: str
    actual: str

    @property
    def reason(self) -> str:
        """Render the `reason` field required by the `06` §5 report shape.

        Returns:
            str: Human-readable expected-versus-actual summary.
        """
        return f"expected {self.expected}, found {self.actual}"

    def as_dict(self) -> dict[str, str]:
        """Return the violation as a machine-readable row.

        Returns:
            dict[str, str]: Keys spanning both fixed report shapes.
        """
        return {
            "rule_id": self.rule,
            "severity": self.severity,
            "location": self.location,
            "expected": self.expected,
            "actual": self.actual,
            "reason": self.reason,
        }


class ContractViolationError(Exception):
    """Raised when an operation would break a contract rule.

    Operations that mutate the freeze ledger raise rather than return findings:
    a freeze is a transaction, and a half-applied freeze would leave the ledger
    asserting a hash nobody agreed to. Read-only checks return `Violation`
    lists instead, so a checker can report every breach in one pass.
    """

    def __init__(self, violation: Violation) -> None:
        super().__init__(f"[{violation.rule}] {violation.location}: {violation.reason}")
        self.violation = violation
