"""The jog-session preflight orchestrator and its report.

`JogSessionPreflight.run` gathers one result per precondition and hands back a
`PreflightReport` whose `may_enable_torque` is the plain conjunction of all five. Two
structural properties make "warn then proceed" — the WP's named FAIL_BLOCKING negative
branch — unrepresentable rather than merely discouraged:

- The report refuses construction unless it carries exactly one result per
  `PreflightCheck`. A check can therefore never be silently dropped; forgetting one is
  a build-time error, not a quietly weaker gate.
- `may_enable_torque` is `all(passed)`. A single failed check forces the aggregate
  false, so no check can fail yet let torque proceed.

The orchestrator is pure: it takes already-gathered evidence (`PreflightInputs`) and
holds no CAN handle, no lock, and no subprocess. Gathering that evidence — probing the
lock, parsing `ip link show`, reading the RIDs — happens at the call site, which keeps
the decision testable with synthetic inputs and keeps the hardware-deferred RID read
out of the decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation import SafetyLimits
from backend.can.link import LinkState
from backend.can.lock import LockState
from backend.preflight.checks import (
    check_can_fd,
    check_clamp_canon,
    check_rid_crosscheck,
    check_side,
    check_writer_lock,
)
from backend.preflight.model import CheckResult, PreflightCheck, RidCrosscheck
from contracts.plugin.config import Side


@dataclass(frozen=True)
class PreflightInputs:
    """The gathered evidence one jog-session preflight decides over.

    Attributes:
        rid: The RID 21/22/23 cross-check evidence (confirmed or hardware-deferred).
        side: The selected arm side, or None when unspecified.
        link: The parsed CAN link state, or None when unread.
        lock_state: This process's view of the interface's writer lock.
        clamp_canon: The selected canonical clamp limit set, or None when unselected.
    """

    rid: RidCrosscheck
    side: Side | None
    link: LinkState | None
    lock_state: LockState
    clamp_canon: SafetyLimits | None


@dataclass(frozen=True)
class PreflightReport:
    """The verdict of one jog-session preflight over all five preconditions.

    Construction validates completeness: exactly one result per `PreflightCheck`, so a
    dropped check is impossible to represent. `may_enable_torque` is the conjunction of
    every result, which is what makes a failed check block rather than warn.

    Attributes:
        results: One result per precondition, in `PreflightCheck` declaration order.
    """

    results: tuple[CheckResult, ...]

    def __post_init__(self) -> None:
        """Reject a report that does not account for every precondition exactly once."""
        seen = [result.check for result in self.results]
        if sorted(item.value for item in seen) != sorted(item.value for item in PreflightCheck):
            raise ValueError(
                "a preflight report must carry exactly one result per PreflightCheck; "
                f"got {[item.value for item in seen]}"
            )

    @property
    def may_enable_torque(self) -> bool:
        """Whether torque-ON is permitted: true only when every precondition passed.

        Returns:
            (bool) The conjunction of all five check results.
        """
        return all(result.passed for result in self.results)

    def failures(self) -> tuple[CheckResult, ...]:
        """Return the failed checks, in order.

        Returns:
            (tuple[CheckResult, ...]) Every result whose precondition did not hold.
        """
        return tuple(result for result in self.results if not result.passed)

    def blocking_summary(self) -> str:
        """Render the blocking preconditions and their evidence, one per line.

        Returns:
            (str) A newline-joined `<check>: <detail>` for each failure, or a single
            line stating torque-ON is permitted when nothing blocked.
        """
        failures = self.failures()
        if not failures:
            return "torque-ON permitted: all five preflight preconditions passed"
        header = f"torque-ON BLOCKED by {len(failures)} preflight precondition(s):"
        lines = [f"  - {result.check.value}: {result.detail}" for result in failures]
        return "\n".join([header, *lines])


class JogSessionPreflight:
    """Runs the five torque-ON preconditions for a jog session.

    Holds nothing: it is a pure decision over `PreflightInputs`. The single method
    exists so the preconditions run in one fixed place and produce one complete report,
    rather than being scattered across a torque-ON caller that could forget one.
    """

    def run(self, inputs: PreflightInputs) -> PreflightReport:
        """Evaluate all five preconditions and assemble the report.

        Args:
            inputs: The gathered evidence for this session.

        Returns:
            (PreflightReport) One result per precondition; `may_enable_torque` is their
            conjunction.
        """
        results = (
            check_rid_crosscheck(inputs.rid),
            check_side(inputs.side),
            check_can_fd(inputs.link),
            check_writer_lock(inputs.lock_state),
            check_clamp_canon(inputs.clamp_canon),
        )
        return PreflightReport(results=results)
