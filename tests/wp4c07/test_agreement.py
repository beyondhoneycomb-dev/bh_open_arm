"""The disagreement aggregator — precision/recall with the human label as truth.

`02c` §3.7 인터페이스 계약: `AgreementReport{n_compared, agreement_rate, precision,
recall, disagreement_by_tag}`, precision/recall computed against the HUMAN label
(the Q11 discipline). This test pins the arithmetic on a worked example, the
None-when-undefined behaviour, the pairing/provenance guards, and that
`disagreement_by_tag` joins by committed taxonomy value (refusing an unknown one).
"""

from __future__ import annotations

import pytest

from backend.eval.autojudge import (
    AgreementError,
    aggregate_agreement,
    pair_judgments,
)
from backend.eval.autojudge.constants import DISAGREEMENT_NO_TAG
from backend.eval.taxonomy.tags import FailureTag
from tests.wp4c07.support import human, model, pair

_COLLISION = FailureTag.COLLISION.value
_TIMEOUT = FailureTag.TIMEOUT.value


def test_worked_example_rates_and_precision_recall() -> None:
    """A 4-pair example fixes agreement_rate, precision, recall, and the tag histogram.

    positive class = success, human = truth:
    - (1) human T / model T  -> TP, agree
    - (2) human F[collision] / model T -> FP, disagree (VLM over-called success)
    - (3) human T / model F -> FN, disagree (no human tag)
    - (4) human F[timeout] / model F -> TN, agree
    n=4, agree=2 -> agreement 0.5; TP=1 FP=1 FN=1 -> precision 0.5, recall 0.5.
    """
    pairs = [
        pair("t", 1, human_success=True, model_success=True),
        pair("t", 2, human_success=False, model_success=True, human_failure_tags=(_COLLISION,)),
        pair("t", 3, human_success=True, model_success=False),
        pair("t", 4, human_success=False, model_success=False, human_failure_tags=(_TIMEOUT,)),
    ]
    report = aggregate_agreement(pairs)
    assert report.n_compared == 4
    assert report.agreement_rate == 0.5
    assert report.disagreement_rate == 0.5
    assert report.precision == 0.5
    assert report.recall == 0.5
    assert report.disagreement_by_tag == {_COLLISION: 1, DISAGREEMENT_NO_TAG: 1}


def test_precision_none_when_model_predicts_no_success() -> None:
    """No predicted positives -> precision is None, never a silent zero."""
    pairs = [
        pair("t", 1, human_success=True, model_success=False),
        pair("t", 2, human_success=True, model_success=False),
    ]
    report = aggregate_agreement(pairs)
    assert report.precision is None
    assert report.recall == 0.0


def test_recall_none_when_human_labels_no_success() -> None:
    """No actual positives -> recall is None."""
    pairs = [
        pair("t", 1, human_success=False, model_success=False, human_failure_tags=(_TIMEOUT,)),
        pair("t", 2, human_success=False, model_success=True, human_failure_tags=(_COLLISION,)),
    ]
    report = aggregate_agreement(pairs)
    assert report.recall is None
    assert report.precision == 0.0


def test_pairing_joins_on_episode_identity() -> None:
    """Only episodes present on both sides pair; unmatched ones are excluded."""
    humans = [human("t", 1, True), human("t", 2, False, failure_tags=(_COLLISION,))]
    models = [model("t", 2, True), model("t", 3, True)]
    pairs = pair_judgments(humans, models)
    assert {p.seed for p in pairs} == {2}
    (only,) = pairs
    assert only.human_success is False
    assert only.model_success is True
    assert only.human_failure_tags == (_COLLISION,)


def test_pairing_refuses_crossed_provenance() -> None:
    """The human side must be HUMAN and the model side MODEL."""
    with pytest.raises(AgreementError):
        pair_judgments([model("t", 1, True)], [model("t", 1, True)])
    with pytest.raises(AgreementError):
        pair_judgments([human("t", 1, True)], [human("t", 1, True)])


def test_unknown_failure_tag_is_refused() -> None:
    """A human failure tag not in the committed taxonomy is refused (value-join)."""
    pairs = [
        pair("t", 1, human_success=False, model_success=True, human_failure_tags=("nonsense",))
    ]
    with pytest.raises(AgreementError):
        aggregate_agreement(pairs)


def test_empty_pairs_refused() -> None:
    """No pairs -> no agreement rate exists; refused rather than dividing by zero."""
    with pytest.raises(AgreementError):
        aggregate_agreement([])
