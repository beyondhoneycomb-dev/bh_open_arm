"""The four IK-failure conditions as distinct fault codes (14 FR-OPS-043).

FR-OPS-043 requires IK failure to be detected as four *separately distinguishable*
conditions, never collapsed into a single "IK failed" verdict — a merged code hides
which failure fired, and the four demand different operator responses (an
unreachable target is not a limit-buster). Each condition therefore owns one
``OA-IK-00x`` code, and ``FaultReporter`` keeps them apart by construction: it is
keyed by code and never coalesces two conditions into one entry.

The four (FR-OPS-043 ①–④):

- ``OA-IK-001`` — ``solve() → None``: the constrained QP found no solution and the
  unconstrained fallback was disabled (the default), so no joint command exists.
- ``OA-IK-002`` — EE residual exceeded: ``‖p_target − FK(q_solved)‖`` past the
  configured ``ik_residual_max_m``. A solve that converges numerically can still
  point the end-effector at the wrong place; this is the only condition that
  inspects the *result*, not the solver's own signal.
- ``OA-IK-003`` — unconstrained fallback fired: the QP failed and the ``limits=[]``
  retry ran (only reachable with the fallback explicitly enabled). Each firing is
  one fault — a fallback that yields a solution has still discarded the soft limits
  (12 FR-SAF-016), so it is loud, never silent.
- ``OA-IK-004`` — joint-limit clamp: the solution left the LeRobot soft limits and
  was clamped back. On the constrained path ``ConfigurationLimit`` makes this
  unreachable; it appears when the unconstrained fallback produced an out-of-limit
  solution.

Any one of the four transitions the adapter to HOLD and holds the last valid joint
angles (FR-OPS-043); the code is the record of *why*.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IkFaultCode(Enum):
    """One code per FR-OPS-043 failure condition; the value is the ``OA-IK-*`` id.

    Four distinct members, so a reporter cannot merge two conditions into a single
    "IK failure" bucket (FR-OPS-043 forbids exactly that).
    """

    SOLVE_NONE = "OA-IK-001"
    EE_RESIDUAL_EXCEEDED = "OA-IK-002"
    UNCONSTRAINED_FALLBACK = "OA-IK-003"
    JOINT_LIMIT_CLAMP = "OA-IK-004"


@dataclass(frozen=True)
class IkFault:
    """A single detected IK failure, carrying its distinct code and context.

    Attributes:
        code: The FR-OPS-043 condition that fired.
        detail: Human-readable context for the operator log.
        joint: The joint name a per-joint condition (clamp) implicates, else None.
        magnitude: The scalar a condition quantifies — residual metres for
            ``EE_RESIDUAL_EXCEEDED``, clamp overshoot radians for
            ``JOINT_LIMIT_CLAMP`` — else None.
    """

    code: IkFaultCode
    detail: str
    joint: str | None = None
    magnitude: float | None = None


class FaultReporter:
    """Collects IK faults while keeping the four conditions distinctly coded.

    Not thread-safe; one reporter belongs to one solve cycle on one thread. The
    single invariant it enforces is FR-OPS-043's: faults are recorded under their
    own ``OA-IK-*`` code and never coalesced, so ``counts_by_code`` can always show
    the four apart. A per-cycle reporter is cleared by ``reset`` between solves.
    """

    def __init__(self) -> None:
        """Initialize an empty reporter."""
        self._faults: list[IkFault] = []

    def report(self, fault: IkFault) -> None:
        """Record one fault under its own code.

        Args:
            fault: The detected failure to record.
        """
        self._faults.append(fault)

    def reset(self) -> None:
        """Drop all faults recorded so far, readying the reporter for a new cycle."""
        self._faults = []

    @property
    def faults(self) -> tuple[IkFault, ...]:
        """Return the faults recorded this cycle, in report order."""
        return tuple(self._faults)

    @property
    def any_fault(self) -> bool:
        """Return whether any fault was recorded this cycle (the HOLD trigger)."""
        return bool(self._faults)

    def codes(self) -> tuple[IkFaultCode, ...]:
        """Return the distinct codes recorded this cycle, in first-seen order."""
        seen: list[IkFaultCode] = []
        for fault in self._faults:
            if fault.code not in seen:
                seen.append(fault.code)
        return tuple(seen)

    def counts_by_code(self) -> dict[IkFaultCode, int]:
        """Return how many times each code fired this cycle.

        Returns:
            (dict[IkFaultCode, int]) Code to firing count; absent codes omitted.
        """
        counts: dict[IkFaultCode, int] = {}
        for fault in self._faults:
            counts[fault.code] = counts.get(fault.code, 0) + 1
        return counts
