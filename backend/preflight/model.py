"""The five torque-ON preconditions and the per-check result they each produce.

WP-2A-09 makes torque-ON a gated act: before a jog session may enable torque, five
preconditions must each hold. This module is the vocabulary — one distinct code per
precondition (a merged "rejected" code would leave an audit unable to say *which*
precondition blocked, the same distinctness the safety filter keeps for its eight
checks) and the immutable result of running one check.

`RidCrosscheck` is the one input that carries a deferral in its type. The live RID
21/22/23 read needs sixteen powered motors, which this host does not have, so the
evidence is either a *confirmed* evaluation (real, via the re-verification hook, or
synthetic, in the offline gate tests) or *unavailable* with a stated reason. There is
no third state, and the absence of a confirmed read is fail-closed: an unavailable
cross-check blocks torque-ON rather than waving it through.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.can.rid.evaluate import DumpEvaluation


class PreflightCheck(Enum):
    """The five torque-ON preconditions (`02b` WP-2A-09 acceptance ①–⑤).

    Each value is a distinct code so a block can always name the precondition that
    failed; the report refuses to be built unless every one of these is accounted for.
    """

    RID_CROSSCHECK = "rid_crosscheck"  # ① RID 21/22/23 vs MOTOR_LIMIT_PARAMS.
    SIDE_SPECIFIED = "side_specified"  # ② --robot.side set (12 FR-SAF-070).
    CAN_FD_LINK = "can_fd_link"  # ③ link is CAN-FD at the required rates (01 FR-SYS-006).
    WRITER_LOCK = "writer_lock"  # ④ this process holds the WP-0B-01 writer lock.
    CLAMP_CANON = "clamp_canon"  # ⑤ a canonical clamp limit set is selected (12 FR-SAF-045).


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one precondition check.

    Attributes:
        check: Which precondition this result is for.
        passed: True when the precondition holds. A false result blocks torque-ON;
            it is never downgraded to a warning (that downgrade is the WP's named
            FAIL_BLOCKING negative branch).
        detail: Human-readable evidence — on a block, it names exactly what failed
            (a limit mismatch, an unset side, the holder PID of a foreign lock, …),
            so the refusal is attributable rather than a bare "no".
    """

    check: PreflightCheck
    passed: bool
    detail: str


@dataclass(frozen=True)
class RidCrosscheck:
    """Evidence for the RID 21/22/23 cross-check, carrying its own deferral.

    Exactly one of the two fields is set. `evaluation` is a confirmed read judged by
    `backend.can.rid.evaluate` — real bytes from the re-verification hook, or synthetic
    bytes in the offline gate tests. `unavailable_reason` states why no confirmed read
    exists (the live sixteen-motor read cannot run on a host with no motors); that
    state blocks torque-ON fail-closed, never passes it.

    Attributes:
        evaluation: The judged RID read, or None when no confirmed read exists.
        unavailable_reason: Why the cross-check could not be confirmed, or None when
            `evaluation` is present.
    """

    evaluation: DumpEvaluation | None
    unavailable_reason: str | None

    @classmethod
    def confirmed(cls, evaluation: DumpEvaluation) -> RidCrosscheck:
        """Wrap a confirmed RID evaluation the torque gate will judge.

        Args:
            evaluation: The judged sixteen-/eight-motor read.

        Returns:
            (RidCrosscheck) Evidence in the confirmed state.
        """
        return cls(evaluation=evaluation, unavailable_reason=None)

    @classmethod
    def unavailable(cls, reason: str) -> RidCrosscheck:
        """State that no confirmed RID read exists, and why.

        Args:
            reason: Why the live cross-check could not be performed.

        Returns:
            (RidCrosscheck) Evidence in the unavailable state, which blocks torque-ON.
        """
        return cls(evaluation=None, unavailable_reason=reason)
