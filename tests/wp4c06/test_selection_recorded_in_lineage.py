"""CG-4C-06f — the selection decision is recorded in lineage (who, on what basis).

`02c` §3.6: a checkpoint selection is recorded THROUGH the committed WP-4A-05 lineage
store, so it is discoverable from the checkpoint's lineage, and it carries who made
it and on what basis. A decision cannot be recorded on undetermined evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.eval.selection import (
    CONDITION_NOMINAL,
    SelectionDecision,
    SelectionDecisionError,
    SelectionDecisionRecorder,
)
from backend.training.lineage import TrainingLineageError, TrainingLineageStore
from tests.wp4c06 import support

_A = support.checkpoint("/runs/A", 1000)
_B = support.checkpoint("/runs/B", 1000)


def _determinate_result():  # type: ignore[no-untyped-def]
    """A SELECTED result: A (0.95) separates above B (0.25)."""
    table = support.table_of(
        support.scorecard(_A, 38, 40, seed0=0),
        support.scorecard(_A, 38, 40, seed0=40),
        support.scorecard(_B, 10, 40, seed0=1000),
        support.scorecard(_B, 10, 40, seed0=1040),
    )
    return table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)


def _undetermined_result():  # type: ignore[no-untyped-def]
    """An UNDETERMINED result: overlapping CIs."""
    table = support.table_of(
        support.scorecard(_A, 22, 40, seed0=0),
        support.scorecard(_A, 22, 40, seed0=40),
        support.scorecard(_B, 20, 40, seed0=1000),
        support.scorecard(_B, 20, 40, seed0=1040),
    )
    return table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)


def _recorder(tmp_path: Path) -> tuple[SelectionDecisionRecorder, TrainingLineageStore]:
    """A recorder bound to a fresh WP-4A-05 lineage store under tmp_path."""
    store = TrainingLineageStore(tmp_path / "lineage")
    return SelectionDecisionRecorder(tmp_path / "decisions", store), store


def test_decision_is_recorded_in_lineage(tmp_path: Path) -> None:
    """The decision id is read back FROM the lineage store, not just the local log."""
    recorder, store = _recorder(tmp_path)
    try:
        decision = SelectionDecision.from_result(
            _determinate_result(),
            decision_id="sel-001",
            selected_by="operator:kim",
            lineage_ref="/runs/A@1000",
        )
        recorder.record(decision)
        assert "sel-001" in store.eval_reports_of(_A)
        assert recorder.lineage_decision_ids(_A) == ("sel-001",)
    finally:
        store.close()


def test_decision_carries_who_and_basis(tmp_path: Path) -> None:
    """The recorded decision names who selected and on what basis (CG-4C-06f)."""
    recorder, store = _recorder(tmp_path)
    try:
        decision = SelectionDecision.from_result(
            _determinate_result(), "sel-002", "operator:lee", "/runs/A@1000"
        )
        recorder.record(decision)
        (stored,) = recorder.decisions_of(_A)
        assert stored.selected_by == "operator:lee"
        assert stored.basis.strip()
        assert stored.selected_checkpoint == _A
    finally:
        store.close()


def test_undetermined_result_cannot_be_recorded() -> None:
    """A decision cannot be built on undetermined evidence (no checkpoint to select)."""
    with pytest.raises(SelectionDecisionError):
        SelectionDecision.from_result(
            _undetermined_result(), "sel-003", "operator:kim", "/runs/A@1000"
        )


def test_empty_who_or_basis_is_refused() -> None:
    """A decision missing who or basis is refused at validation."""
    with pytest.raises(SelectionDecisionError):
        SelectionDecision(
            decision_id="d",
            selected_checkpoint=_A,
            task="pick",
            condition=CONDITION_NOMINAL,
            selected_by="   ",
            basis="ci-separated",
            lineage_ref="/runs/A@1000",
        ).validate()


def test_relinking_a_decision_id_to_another_checkpoint_is_refused(tmp_path: Path) -> None:
    """Lineage refuses to point one decision id at two checkpoints."""
    recorder, store = _recorder(tmp_path)
    try:
        recorder.record(
            SelectionDecision.from_result(_determinate_result(), "sel-004", "op", "/runs/A@1000")
        )
        clash = SelectionDecision(
            decision_id="sel-004",
            selected_checkpoint=_B,
            task="pick",
            condition=CONDITION_NOMINAL,
            selected_by="op",
            basis="x",
            lineage_ref="/runs/B@1000",
        )
        with pytest.raises(TrainingLineageError):
            recorder.record(clash)
    finally:
        store.close()
