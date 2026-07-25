"""CG-4C-07c — the sidecar tags `model-judged` distinctly from `human-labeled`.

`FR-SIM-095`: an auto-judged result is recorded as sidecar metadata tagged
`model-judged`, kept distinct from a human-labelled result. The test checks the two
tags are different, that a model episode carries the model tag with its judge and
rationale while a human one carries the human tag with neither, and that the sidecar
type refuses any tag but `model-judged` and refuses a provenance/sidecar mismatch.
"""

from __future__ import annotations

import pytest

from backend.eval.autojudge import (
    SIDECAR_TAG_HUMAN_LABELED,
    SIDECAR_TAG_MODEL_JUDGED,
    JudgedEpisode,
    JudgeSidecar,
    LabelSource,
    sidecar_records,
)
from backend.eval.autojudge.labels import LabelProvenanceError
from tests.wp4c07.support import episode, human, model


def test_the_two_tags_are_distinct() -> None:
    """The model-judged and human-labeled tags are different strings."""
    assert SIDECAR_TAG_MODEL_JUDGED != SIDECAR_TAG_HUMAN_LABELED


def test_model_episode_carries_model_tag() -> None:
    """A MODEL episode reads `model-judged` and carries judge name + rationale."""
    judged = model("pick", 1, True, rationale="cube is in the bin")
    assert judged.sidecar_tag == SIDECAR_TAG_MODEL_JUDGED
    assert judged.sidecar is not None
    assert judged.sidecar.rationale == "cube is in the bin"


def test_human_episode_carries_human_tag_and_no_sidecar() -> None:
    """A HUMAN episode reads `human-labeled` and carries no judge sidecar."""
    judged = human("pick", 1, True)
    assert judged.sidecar_tag == SIDECAR_TAG_HUMAN_LABELED
    assert judged.sidecar is None


def test_sidecar_records_render_distinct_tags() -> None:
    """The rendered sidecars distinguish the two provenances with different tag keys."""
    records = sidecar_records([human("pick", 1, True), model("pick", 2, False)])
    tags = [record["provenance_tag"] for record in records]
    assert tags == [SIDECAR_TAG_HUMAN_LABELED, SIDECAR_TAG_MODEL_JUDGED]
    human_record, model_record = records
    assert "model_name" not in human_record
    assert model_record["model_name"] == "cosmos-reason-2"
    assert "rationale" in model_record


def test_sidecar_refuses_a_non_model_tag() -> None:
    """A `JudgeSidecar` cannot be tagged anything but `model-judged`."""
    with pytest.raises(LabelProvenanceError):
        JudgeSidecar(model_name="x", rationale="y", tag=SIDECAR_TAG_HUMAN_LABELED)


def test_model_without_sidecar_is_refused() -> None:
    """A MODEL-sourced episode with no sidecar is refused — provenance must be tagged."""
    with pytest.raises(LabelProvenanceError):
        JudgedEpisode(episode=episode("pick", 1, True), source=LabelSource.MODEL)


def test_human_with_sidecar_is_refused() -> None:
    """A HUMAN-sourced episode carrying a model sidecar is refused."""
    with pytest.raises(LabelProvenanceError):
        JudgedEpisode(
            episode=episode("pick", 1, True),
            source=LabelSource.HUMAN,
            sidecar=JudgeSidecar(model_name="x", rationale="y"),
        )
