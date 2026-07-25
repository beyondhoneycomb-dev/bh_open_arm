"""CG-4C-07b — disagreement over threshold disables the auto-judge and requires humans.

`FR-INF-079`: when the auto-judge/human disagreement rate exceeds the threshold, the
auto-judge is disabled and human labels are required — a required NORMAL transition,
not a gate failure (`02c` §3.7 음성 분기 ②). The test checks the transition actually
fires (and does not fire below threshold), and that an AMBIGUOUS human label is the
second disable trigger (`02c` §3.4). The trigger never yields ENABLED.
"""

from __future__ import annotations

from backend.eval.autojudge import (
    AutoJudgeState,
    aggregate_agreement,
    default_threshold,
    evaluate_disable,
)
from backend.eval.autojudge.trigger import (
    REASON_AMBIGUOUS,
    REASON_DISAGREEMENT,
    REASON_NOT_TRIGGERED,
)
from tests.wp4c07.support import pair

_HIGH_THRESHOLD = 0.5


def _report(disagreements: int, total: int):
    """Build a real `AgreementReport` with `disagreements` of `total` pairs disagreeing."""
    pairs = []
    for index in range(total):
        disagree = index < disagreements
        # human always success; model disagrees on the first `disagreements` pairs.
        pairs.append(pair("t", index, human_success=True, model_success=not disagree))
    return aggregate_agreement(pairs)


def test_disagreement_over_threshold_disables() -> None:
    """8/10 disagreement with threshold 0.5 -> disabled, human labels required."""
    report = _report(disagreements=8, total=10)
    decision = evaluate_disable(
        AutoJudgeState.ENABLED, report, human_failure_tag_values=(), threshold=_HIGH_THRESHOLD
    )
    assert decision.triggered is True
    assert decision.next_state is AutoJudgeState.DISABLED_REQUIRE_HUMAN
    assert decision.require_human_labels is True
    assert decision.reason == REASON_DISAGREEMENT


def test_disagreement_within_threshold_stays_enabled() -> None:
    """2/10 disagreement with threshold 0.5 -> unchanged, still enabled."""
    report = _report(disagreements=2, total=10)
    decision = evaluate_disable(
        AutoJudgeState.ENABLED, report, human_failure_tag_values=(), threshold=_HIGH_THRESHOLD
    )
    assert decision.triggered is False
    assert decision.next_state is AutoJudgeState.ENABLED
    assert decision.require_human_labels is False
    assert decision.reason == REASON_NOT_TRIGGERED


def test_threshold_is_strict_exceeds_not_reaches() -> None:
    """A disagreement rate exactly at the threshold does not trip (spec: 'exceeds')."""
    report = _report(disagreements=5, total=10)  # rate == 0.5
    decision = evaluate_disable(
        AutoJudgeState.ENABLED, report, human_failure_tag_values=(), threshold=_HIGH_THRESHOLD
    )
    assert decision.disagreement_rate == 0.5
    assert decision.triggered is False


def test_ambiguous_human_label_disables_even_below_threshold() -> None:
    """A human AMBIGUOUS tag disables regardless of the disagreement rate (`02c` §3.4)."""
    report = _report(disagreements=0, total=10)  # perfect agreement
    decision = evaluate_disable(
        AutoJudgeState.ENABLED,
        report,
        human_failure_tag_values=("ambiguous",),
        threshold=_HIGH_THRESHOLD,
    )
    assert decision.triggered is True
    assert decision.next_state is AutoJudgeState.DISABLED_REQUIRE_HUMAN
    assert decision.reason == REASON_AMBIGUOUS


def test_trigger_never_yields_enabled() -> None:
    """Across a spread of rates the trigger never produces ENABLED — it is one-way."""
    for disagreements in range(0, 11):
        report = _report(disagreements=disagreements, total=10)
        decision = evaluate_disable(
            AutoJudgeState.ENABLED,
            report,
            human_failure_tag_values=(),
            threshold=default_threshold(),
        )
        assert decision.next_state in (
            AutoJudgeState.ENABLED,
            AutoJudgeState.DISABLED_REQUIRE_HUMAN,
        )
        if decision.triggered:
            assert decision.next_state is AutoJudgeState.DISABLED_REQUIRE_HUMAN
