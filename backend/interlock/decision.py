"""The interlock's decision record — how it consumes a dry-run report (`02b` §1.2).

WP-2A-00 owns no check and no report *schema*: those are Wave 0-C's
(``sim.dryrun.violation.DryRunVerdict`` and its six ``DryRunCheck`` codes). What it
owns is the *consumption* of that report at the real-send boundary — the record
that says whether a given dry-run verdict permitted real transmission and, when it
did not, which of the six checks blocked it, at which sim time, on which joint, and
by how much. That per-violation locus is not re-derived here; it is carried through
unchanged from the ``Violation`` records the Wave 0-C checkers stamped, so the
interlock's report and the dry-run's report never disagree about what was hit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sim.dryrun.violation import DryRunVerdict, Violation


class InterlockState(Enum):
    """The barrier's real-send posture after consuming a verdict.

    ``PENDING`` is the fail-closed default: a barrier that has evaluated nothing
    permits no real transmission. ``ARMED`` is reached only by a passing verdict or
    a sanctioned modal override; ``BLOCKED`` records a hard block on a failing one.
    """

    PENDING = "pending"
    ARMED = "armed"
    BLOCKED = "blocked"


class RealTransitionBlockedError(RuntimeError):
    """Raised when a real transition is attempted while the barrier is not armed.

    `02b` §1.2 WP-2A-00: a real (`REAL`) transition is forbidden until a dry-run has
    passed the interlock. This is the runtime face of that forbiddance.
    """


@dataclass(frozen=True)
class InterlockDecision:
    """One real-send gating decision, built by consuming a dry-run verdict.

    Attributes:
        state: ``ARMED`` when real transmission is permitted, ``BLOCKED`` otherwise.
        via_modal_confirm: True when an ``ARMED`` decision came from the one
            sanctioned operator override rather than a clean passing verdict.
        verdict: The Wave 0-C dry-run verdict this decision consumed.
    """

    state: InterlockState
    via_modal_confirm: bool
    verdict: DryRunVerdict

    @property
    def permits_real_send(self) -> bool:
        """Whether this decision authorises real transmission."""
        return self.state is InterlockState.ARMED

    @property
    def blocking_violations(self) -> tuple[Violation, ...]:
        """The violations that blocked real-send, each carrying item/sim_t/joint/overage.

        Returns:
            (tuple[Violation, ...]) The verdict's violations when blocked (the report
            the interlock leaves behind, ③/① evidence); empty when armed.
        """
        if self.permits_real_send:
            return ()
        return self.verdict.violations
