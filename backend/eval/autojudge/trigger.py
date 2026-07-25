"""The auto-disable trigger — disagreement over threshold, or an AMBIGUOUS human label.

`FR-INF-079`: when the auto-judge/human disagreement rate exceeds a threshold, the
auto-judge is disabled and human labels are required. `02c` §3.4 adds the second
trigger: a human `AMBIGUOUS` tag ("the labeler could not decide") is by definition the
auto-judge disable trigger — if a human cannot decide, a model verdict is not to be
trusted for that task.

This is the ONLY reverse transition in the package: `evaluate_disable` moves an ENABLED
auto-judge to DISABLED_REQUIRE_HUMAN, and never the other way. It cannot enable — it
constructs no `AutoJudgeState.ENABLED` — so the Q11 gate (`enablement`) remains the
sole enable path (CG-4C-07e). Disabling is `FR-INF-079`'s required normal transition,
not a gate failure (`02c` §3.7 음성 분기 ②).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.eval.autojudge.agreement import AgreementReport
from backend.eval.autojudge.constants import DEFAULT_DISAGREEMENT_THRESHOLD
from backend.eval.autojudge.enablement import AutoJudgeState

# WP-4C-04 taxonomy consumption: the AMBIGUOUS tag is, per `02c` §3.4, the auto-judge
# disable trigger. The committed `FailureTag.AMBIGUOUS` value is imported (never
# redefined) so this trigger reads the canonical token rather than a local copy of the
# string that could drift from the taxonomy.
from backend.eval.taxonomy.tags import FailureTag

_AMBIGUOUS_TAG_VALUE = FailureTag.AMBIGUOUS.value

# The reasons an auto-judge is disabled, so a caller can tell a disagreement-driven
# disable from an ambiguity-driven one from "not triggered".
REASON_NOT_TRIGGERED = "disagreement within threshold; auto-judge stays enabled"
REASON_DISAGREEMENT = "disagreement rate exceeded threshold (FR-INF-079)"
REASON_AMBIGUOUS = "a human AMBIGUOUS label was present (02c §3.4 disable trigger)"


@dataclass(frozen=True)
class DisableDecision:
    """The outcome of evaluating the auto-disable triggers (`FR-INF-079`).

    Attributes:
        triggered: Whether a disable fired.
        next_state: The resulting state — `DISABLED_REQUIRE_HUMAN` when triggered,
            else the state passed in (unchanged).
        require_human_labels: True when the auto-judge is disabled and human labelling
            must resume (always the case when `triggered`).
        reason: Which trigger fired, or that none did.
        disagreement_rate: The rate that was compared against the threshold.
        threshold: The threshold compared against.
    """

    triggered: bool
    next_state: AutoJudgeState
    require_human_labels: bool
    reason: str
    disagreement_rate: float
    threshold: float


def has_ambiguous_label(human_failure_tag_values: Sequence[str]) -> bool:
    """Whether any human failure-tag value is the AMBIGUOUS disable trigger.

    Args:
        human_failure_tag_values: Human-assigned failure-tag values, by value.

    Returns:
        (bool) True when `AMBIGUOUS` is among them.
    """
    return _AMBIGUOUS_TAG_VALUE in set(human_failure_tag_values)


def evaluate_disable(
    current_state: AutoJudgeState,
    report: AgreementReport,
    human_failure_tag_values: Sequence[str],
    threshold: float,
) -> DisableDecision:
    """Decide whether to disable the auto-judge and require human labels.

    Two triggers, either sufficient: the disagreement rate strictly exceeds the
    threshold (`FR-INF-079`), or a human `AMBIGUOUS` label is present (`02c` §3.4).
    When either fires the state moves to `DISABLED_REQUIRE_HUMAN`; otherwise the state
    is returned unchanged. This transition is one-way — it never produces ENABLED.

    Args:
        current_state: The auto-judge's state before evaluation.
        report: The disagreement aggregate to read `disagreement_rate` from.
        human_failure_tag_values: The human failure-tag values seen (for the AMBIGUOUS
            trigger).
        threshold: The disagreement threshold; a rate strictly above it trips.

    Returns:
        (DisableDecision) The transition and the reason.
    """
    ambiguous = has_ambiguous_label(human_failure_tag_values)
    over_threshold = report.disagreement_rate > threshold

    if ambiguous:
        reason = REASON_AMBIGUOUS
    elif over_threshold:
        reason = REASON_DISAGREEMENT
    else:
        reason = REASON_NOT_TRIGGERED

    triggered = ambiguous or over_threshold
    next_state = AutoJudgeState.DISABLED_REQUIRE_HUMAN if triggered else current_state
    return DisableDecision(
        triggered=triggered,
        next_state=next_state,
        require_human_labels=triggered,
        reason=reason,
        disagreement_rate=report.disagreement_rate,
        threshold=threshold,
    )


def default_threshold() -> float:
    """Return the placeholder disagreement threshold (`02c` §1.5 explicit placeholder).

    Returns:
        (float) `DEFAULT_DISAGREEMENT_THRESHOLD` — a named placeholder, not a measured
            operating point (the real figure needs the DEFERRED precision/recall run).
    """
    return DEFAULT_DISAGREEMENT_THRESHOLD
