"""The Q11-order gate — the only path to enabling the auto-judge (`11` §5-Q11).

`02c` §3.7 착수 조건 makes the order the whole WP: (1) collect human labels -> (2) fix
each task's success criterion in prose -> (3) measure the VLM's precision/recall
against those labels -> (4) only then decide to enable. The reverse — attach the VLM
first, have humans review it — anchors the humans to the model and poisons the ground
truth. And step (2) is a precondition of (3): without a written criterion there is no
VLM prompt and no way to measure label consistency.

This module encodes that as the single gate `enable_autojudge`. It is the ONLY place
`AutoJudgeState.ENABLED` is ever produced (CG-4C-07e): the readiness must be complete
AND in order, or it raises. Nothing else in the package constructs ENABLED — the
disagreement/AMBIGUOUS triggers only ever drive the reverse transition — so there is
no path that enables the auto-judge before the Q11 order is satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.eval.autojudge.constants import (
    Q11_ORDER,
    Q11_STAGE_HUMAN_LABELS,
    Q11_STAGE_PRECISION_RECALL,
    Q11_STAGE_SUCCESS_CRITERIA,
    STATE_DISABLED_INITIAL,
    STATE_DISABLED_REQUIRE_HUMAN,
    STATE_ENABLED,
)


class AutoJudgeState(Enum):
    """The auto-judge lifecycle state (`02c` §3.7, `FR-INF-079`).

    DISABLED_INITIAL is the start: the auto-judge is off and the canon is the human
    label. ENABLED is reachable ONLY through `enable_autojudge` after the Q11 order.
    DISABLED_REQUIRE_HUMAN is the trigger's terminal reverse state — auto-judge off
    and human labels required — never re-enabled without passing the gate again.
    """

    DISABLED_INITIAL = STATE_DISABLED_INITIAL
    ENABLED = STATE_ENABLED
    DISABLED_REQUIRE_HUMAN = STATE_DISABLED_REQUIRE_HUMAN


class Q11OrderError(RuntimeError):
    """Raised when auto-judge enablement is attempted out of the Q11 order.

    This is the enforcement of `02c` §3.7 착수 조건: a request to enable the auto-judge
    before human labels, then criteria, then precision/recall are — in that order —
    satisfied. Refusing is not a failure of this WP; it is the WP working.
    """


@dataclass(frozen=True)
class Q11Readiness:
    """Which Q11 preconditions have been met (`11` §5-Q11 / `02c` §3.7 착수 조건).

    The three flags are the three ordered steps. `satisfied_stages` reads them back in
    canonical order and, critically, stops at the first unmet stage: a later flag set
    while an earlier one is not is an out-of-order state, which `is_in_order` reports
    and the gate refuses — you cannot have measured precision/recall (3) without the
    criteria (2), nor criteria without the labels (1).

    Attributes:
        human_labels_collected: Step (1) — human reference labels gathered.
        success_criteria_defined: Step (2) — per-task success criterion written.
        precision_recall_measured: Step (3) — VLM precision/recall measured on (1)
            against (2).
    """

    human_labels_collected: bool
    success_criteria_defined: bool
    precision_recall_measured: bool

    def _flag(self, stage: str) -> bool:
        """Return the flag for a Q11 stage id."""
        return {
            Q11_STAGE_HUMAN_LABELS: self.human_labels_collected,
            Q11_STAGE_SUCCESS_CRITERIA: self.success_criteria_defined,
            Q11_STAGE_PRECISION_RECALL: self.precision_recall_measured,
        }[stage]

    def is_in_order(self) -> bool:
        """Whether no later Q11 stage is set while an earlier one is unset.

        Returns:
            (bool) True when the set stages form an unbroken prefix of `Q11_ORDER`.
        """
        seen_unmet = False
        for stage in Q11_ORDER:
            if self._flag(stage):
                if seen_unmet:
                    return False
            else:
                seen_unmet = True
        return True

    def all_satisfied(self) -> bool:
        """Whether every Q11 stage is met (a necessary condition for enablement)."""
        return all(self._flag(stage) for stage in Q11_ORDER)

    def first_unmet_stage(self) -> str | None:
        """Return the first Q11 stage not yet met, or None when all are met.

        Returns:
            (str | None) The earliest unmet stage id in `Q11_ORDER`, else None.
        """
        for stage in Q11_ORDER:
            if not self._flag(stage):
                return stage
        return None


def can_enable_autojudge(readiness: Q11Readiness) -> bool:
    """Whether the Q11 order permits enabling the auto-judge (predicate only).

    A pure predicate: it constructs no state and enables nothing, so it is safe to call
    for UI/preview. Enablement requires every stage met AND in order.

    Args:
        readiness: The Q11 preconditions met so far.

    Returns:
        (bool) True iff enablement is permitted.
    """
    return readiness.all_satisfied() and readiness.is_in_order()


def enable_autojudge(readiness: Q11Readiness) -> AutoJudgeState:
    """The gate: return `AutoJudgeState.ENABLED`, or refuse if the Q11 order is unmet.

    This is the sole producer of `AutoJudgeState.ENABLED` in the package (CG-4C-07e).
    It refuses an incomplete or out-of-order readiness rather than enabling anyway, so
    the auto-judge can never be turned on before human labels -> criteria ->
    precision/recall are satisfied in order.

    Args:
        readiness: The Q11 preconditions met so far.

    Returns:
        (AutoJudgeState) `ENABLED` when the order is satisfied.

    Raises:
        Q11OrderError: When a stage is unmet or the stages are out of order.
    """
    if not readiness.is_in_order():
        raise Q11OrderError(
            "Q11 order violated: a later stage is marked done while an earlier one is not "
            f"(order is {' -> '.join(Q11_ORDER)}). Enablement refused."
        )
    unmet = readiness.first_unmet_stage()
    if unmet is not None:
        raise Q11OrderError(
            f"cannot enable the auto-judge before Q11 step {unmet!r} is satisfied "
            f"(order is {' -> '.join(Q11_ORDER)}). Until then the success-rate canon is "
            "the human label (FR-INF-079)."
        )
    return AutoJudgeState.ENABLED
