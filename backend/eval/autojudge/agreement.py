"""The disagreement aggregator — `AgreementReport` with the human label as truth.

`02c` §3.7 인터페이스 계약: `AgreementReport{n_compared, agreement_rate, precision,
recall, disagreement_by_tag}`, and precision/recall are computed with the HUMAN label
as ground truth (the Q11 discipline). This module pairs a human-labelled and a
model-judged label for the same episode and reduces the pairs to that report.

Two decisions carry the spec's intent:

- **Positive class = success.** The asymmetric risk `02c` §3.7 대가 warns about is the
  VLM calling a near-miss a success, which inflates the success rate. Fixing the
  positive class to "success" makes that failure mode legible: a false positive is a
  model-success the human called a failure, so low precision is exactly the dangerous
  bias, not a symmetric disagreement rate that would hide it.
- **`disagreement_by_tag` is keyed by the human's failure tags, by value.** The tags
  are generic string values (the WP-4C-04 data-join, `02c` §3.4) — this joins by
  value and validates each against the committed taxonomy so a typo cannot invent a
  tag. It answers "which failure types does the VLM misjudge"; a disagreement with no
  human failure tag (a human-success the model missed) is counted under an explicit
  no-tag key rather than dropped.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from backend.eval.autojudge.constants import DISAGREEMENT_NO_TAG
from backend.eval.autojudge.labels import JudgedEpisode, LabelSource

# WP-4C-04 taxonomy consumption: the disagreement histogram is keyed by failure-tag
# VALUES (the §3.4 data-join), and this imports the committed `FailureTag` only to
# validate that each value a report is keyed by is a real taxonomy tag — never to
# redefine or re-enumerate the tags. `_KNOWN_TAG_VALUES` is that value set.
from backend.eval.taxonomy.tags import FailureTag

_KNOWN_TAG_VALUES: frozenset[str] = frozenset(tag.value for tag in FailureTag)


class AgreementError(ValueError):
    """Raised when agreement cannot be computed from the given pairs.

    Cases: an empty pairing (no rate exists), a pair whose two sides are not the same
    episode, a pair mixing provenance wrongly (the human side not HUMAN or the model
    side not MODEL), or a human failure tag that is not a known taxonomy value.
    """


@dataclass(frozen=True)
class JudgmentPair:
    """One episode judged by both a human (truth) and the model (prediction).

    Attributes:
        task_id: The episode's task.
        seed: The episode's initial-state seed; with `task_id`, its identity.
        human_success: The canon label (ground truth).
        model_success: The auto-judge's prediction.
        human_failure_tags: The human's failure-tag values for this episode, by value
            (empty on a human-success). Used to key `disagreement_by_tag`.
    """

    task_id: str
    seed: int
    human_success: bool
    model_success: bool
    human_failure_tags: tuple[str, ...]

    @property
    def agrees(self) -> bool:
        """Whether the model prediction matches the human ground truth."""
        return self.human_success == self.model_success


@dataclass(frozen=True)
class AgreementReport:
    """The disagreement aggregate (`02c` §3.7 인터페이스 계약).

    Frozen: a computed summary of a fixed set of pairs. `precision`/`recall` treat
    success as the positive class with the human label as truth; they are `None` when
    undefined (no predicted positives -> precision undefined; no actual positives ->
    recall undefined), never silently zero.

    Attributes:
        n_compared: Number of episodes judged by both a human and the model.
        agreement_rate: Fraction of pairs where model matches human.
        disagreement_rate: `1 - agreement_rate` — the figure the disable trigger reads.
        precision: TP / (TP + FP), or `None` when the model predicted no successes.
        recall: TP / (TP + FN), or `None` when the human labelled no successes.
        disagreement_by_tag: Human failure-tag value -> count, over disagreeing pairs;
            disagreements with no human failure tag counted under `DISAGREEMENT_NO_TAG`.
    """

    n_compared: int
    agreement_rate: float
    disagreement_rate: float
    precision: float | None
    recall: float | None
    disagreement_by_tag: dict[str, int]


def pair_judgments(
    human: Sequence[JudgedEpisode],
    model: Sequence[JudgedEpisode],
) -> tuple[JudgmentPair, ...]:
    """Join human and model labels on episode identity into comparable pairs.

    Only episodes judged by BOTH sides are paired; a human label with no model
    judgement (or vice versa) is not a comparison and is left out. The human side
    must be HUMAN-sourced and the model side MODEL-sourced, or the pairing has crossed
    its provenance and is refused.

    Args:
        human: Human-labelled episodes (each `source is HUMAN`).
        model: Model-judged episodes (each `source is MODEL`).

    Returns:
        (tuple[JudgmentPair, ...]) One pair per episode present on both sides, ordered
            by the human input order.

    Raises:
        AgreementError: When a side carries the wrong provenance.
    """
    for item in human:
        if item.source is not LabelSource.HUMAN:
            raise AgreementError(
                f"the human side must be HUMAN-sourced; got {item.source.value} for "
                f"{item.episode.task_id!r} seed {item.episode.seed}"
            )
    for item in model:
        if item.source is not LabelSource.MODEL:
            raise AgreementError(
                f"the model side must be MODEL-sourced; got {item.source.value} for "
                f"{item.episode.task_id!r} seed {item.episode.seed}"
            )

    model_by_key = {(item.episode.task_id, item.episode.seed): item for item in model}
    pairs: list[JudgmentPair] = []
    for human_item in human:
        key = (human_item.episode.task_id, human_item.episode.seed)
        model_item = model_by_key.get(key)
        if model_item is None:
            continue
        pairs.append(
            JudgmentPair(
                task_id=human_item.episode.task_id,
                seed=human_item.episode.seed,
                human_success=human_item.episode.success,
                model_success=model_item.episode.success,
                human_failure_tags=human_item.episode.failure_tags,
            )
        )
    return tuple(pairs)


def aggregate_agreement(pairs: Sequence[JudgmentPair]) -> AgreementReport:
    """Reduce human/model judgement pairs to an `AgreementReport`.

    precision/recall use success as the positive class and the human label as ground
    truth (Q11 discipline). Each disagreeing pair's human failure-tag values feed
    `disagreement_by_tag`, validated against the committed taxonomy; a tagless
    disagreement is counted under `DISAGREEMENT_NO_TAG`.

    Args:
        pairs: The paired judgements; must be non-empty.

    Returns:
        (AgreementReport) The disagreement aggregate.

    Raises:
        AgreementError: When `pairs` is empty or carries an unknown failure tag.
    """
    if not pairs:
        raise AgreementError("cannot compute agreement over an empty set of pairs")

    n = len(pairs)
    agree = sum(1 for pair in pairs if pair.agrees)
    agreement_rate = agree / n

    true_positive = sum(1 for p in pairs if p.model_success and p.human_success)
    false_positive = sum(1 for p in pairs if p.model_success and not p.human_success)
    false_negative = sum(1 for p in pairs if not p.model_success and p.human_success)

    predicted_positive = true_positive + false_positive
    actual_positive = true_positive + false_negative
    precision = true_positive / predicted_positive if predicted_positive else None
    recall = true_positive / actual_positive if actual_positive else None

    by_tag: Counter[str] = Counter()
    for pair in pairs:
        if pair.agrees:
            continue
        if not pair.human_failure_tags:
            by_tag[DISAGREEMENT_NO_TAG] += 1
            continue
        for tag_value in pair.human_failure_tags:
            if tag_value not in _KNOWN_TAG_VALUES:
                raise AgreementError(
                    f"human failure tag {tag_value!r} is not a known taxonomy value; "
                    "disagreement_by_tag joins by value against the committed WP-4C-04 tags"
                )
            by_tag[tag_value] += 1

    return AgreementReport(
        n_compared=n,
        agreement_rate=agreement_rate,
        disagreement_rate=1.0 - agreement_rate,
        precision=precision,
        recall=recall,
        disagreement_by_tag=dict(by_tag),
    )
