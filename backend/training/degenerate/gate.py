"""The gate that forbids training from starting on an undecided degeneracy.

`FR-TRN-068` / `02c` §1.3 ④: when a degenerate channel is detected, training must
not start until a three-way choice (EXCLUDE / MANUAL_STATS / PROCEED) is recorded
for it — there must be ZERO paths where training begins without the choice being
presented and decided.

The invariant is enforced as a capability token, not a runtime flag: a
`TrainingClearance` is the object a caller must hold to consider a dataset cleared,
and the ONLY site that mints one is `clear_for_training`, which mints it only after
every finding has a matching decision. That single-mint-site property is what makes
`02c` §1.3 ④ a STATIC check (`tests/wp4a03/test_no_bypass.py` parses this package
and proves the token is constructed nowhere else and only past the completeness
raise), rather than a hope that every caller remembered to check.

Structural limit (stated, not papered over): this proves the degenerate subsystem
exposes no bypass. It cannot force a *future* work package to demand the token
before launching `lerobot-train` — that WP owns the launch path (WP-4A-01), which
this band must not edit. What this band guarantees is that a caller who routes
through it cannot obtain a clearance while a finding is undecided.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.training.degenerate.finding import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
)
from backend.training.preflight import PreflightReport, Verdict


class DegenerateGateError(RuntimeError):
    """Raised when a clearance is requested while a degeneracy is unresolved.

    The two blocking cases: the dataset has not passed preflight (degeneracy is
    only meaningful once the observation configuration itself is valid), or at least
    one finding has no recorded decision (`FR-TRN-068`).
    """


@dataclass(frozen=True)
class TrainingClearance:
    """Proof that every degenerate finding was resolved before training.

    This is a capability token: holding one means the gate confirmed a decision for
    every finding. It is minted ONLY by `clear_for_training` — no other construction
    site exists, and `tests/wp4a03/test_no_bypass.py` proves that statically, so a
    clearance cannot be fabricated to skip the check.

    Attributes:
        reviewed_findings: The findings that were presented for decision (possibly
            empty — a clean dataset clears with no findings).
        decisions: The recorded decision per finding.
    """

    reviewed_findings: tuple[DegenerateFinding, ...]
    decisions: tuple[DegenerateDecision, ...]


def present_choices() -> tuple[DegenerateChoice, ...]:
    """Return the three choices that must be offered for every finding (`FR-TRN-068`).

    The set is the full `DegenerateChoice` enum and is the same for every finding, so
    the presentation cannot silently drop an option; a caller renders these against a
    finding and records the operator's pick.

    Returns:
        (tuple[DegenerateChoice, ...]) EXCLUDE, MANUAL_STATS, PROCEED.
    """
    return tuple(DegenerateChoice)


def undecided_findings(
    findings: tuple[DegenerateFinding, ...], decisions: tuple[DegenerateDecision, ...]
) -> tuple[DegenerateFinding, ...]:
    """Return the findings that have no matching decision.

    A finding is decided when some decision carries it (frozen findings compare by
    value, so a decision's `finding` matches the one it resolves).

    Args:
        findings: The detected findings.
        decisions: The recorded decisions.

    Returns:
        (tuple[DegenerateFinding, ...]) The findings still lacking a decision.
    """
    decided = {decision.finding for decision in decisions}
    return tuple(finding for finding in findings if finding not in decided)


def clear_for_training(
    preflight_report: PreflightReport,
    findings: tuple[DegenerateFinding, ...],
    decisions: tuple[DegenerateDecision, ...],
) -> TrainingClearance:
    """Mint a clearance iff preflight passed and every finding is decided.

    This is the sole mint site of `TrainingClearance`. It raises rather than returns
    on either blocking case, so there is no branch that yields a clearance past an
    undecided finding — the property `tests/wp4a03/test_no_bypass.py` verifies.

    Args:
        preflight_report: The WP-4A-02 verdict; degeneracy is judged only on a
            dataset whose observation configuration already passed.
        findings: The detected degenerate findings.
        decisions: The three-way decisions recorded for them.

    Returns:
        (TrainingClearance) The capability token, when cleared.

    Raises:
        DegenerateGateError: When preflight did not pass, or any finding is undecided.
    """
    if preflight_report.verdict is not Verdict.PASS:
        raise DegenerateGateError(
            "dataset did not pass preflight (verdict "
            f"{preflight_report.verdict}); resolve the preflight findings before degeneracy review"
        )

    pending = undecided_findings(findings, decisions)
    if pending:
        located = ", ".join(f"{finding.channel_name} ({finding.norm_mode})" for finding in pending)
        raise DegenerateGateError(
            f"{len(pending)} degenerate channel(s) have no recorded EXCLUDE/MANUAL_STATS/PROCEED "
            f"decision: {located}; training must not start without the three-way choice "
            "(FR-TRN-068)"
        )

    return TrainingClearance(reviewed_findings=findings, decisions=decisions)
