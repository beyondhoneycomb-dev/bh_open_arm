"""CG-4C-07e — no path enables the auto-judge before the Q11 order is satisfied.

`11` §5-Q11 / `02c` §3.7 착수 조건: the order is (1) human labels -> (2) success
criteria -> (3) precision/recall, and only then (4) decide enablement. This test is
behavioural (out-of-order or incomplete readiness is refused; the full in-order
readiness enables) and static (the sole producer of `AutoJudgeState.ENABLED` in the
whole package is `enable_autojudge`, so there is no other path to the enabled state).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from backend.eval.autojudge import (
    AutoJudgeState,
    Q11OrderError,
    Q11Readiness,
    can_enable_autojudge,
    enable_autojudge,
)
from backend.eval.autojudge import enablement as enablement_module

_AUTOJUDGE_DIR = Path(inspect.getfile(enablement_module)).parent


def _readiness(labels: bool, criteria: bool, precision_recall: bool) -> Q11Readiness:
    """Build a `Q11Readiness` from the three stage flags."""
    return Q11Readiness(
        human_labels_collected=labels,
        success_criteria_defined=criteria,
        precision_recall_measured=precision_recall,
    )


def test_full_in_order_readiness_enables() -> None:
    """All three stages met in order -> ENABLED (the positive control)."""
    readiness = _readiness(True, True, True)
    assert can_enable_autojudge(readiness) is True
    assert enable_autojudge(readiness) is AutoJudgeState.ENABLED


def test_no_labels_refuses() -> None:
    """Step (1) unmet -> refused; the canon stays the human label."""
    readiness = _readiness(False, False, False)
    assert can_enable_autojudge(readiness) is False
    with pytest.raises(Q11OrderError):
        enable_autojudge(readiness)


def test_labels_but_no_criteria_refuses() -> None:
    """Step (2) unmet (labels only) -> refused: no criterion, no VLM prompt."""
    readiness = _readiness(True, False, False)
    with pytest.raises(Q11OrderError):
        enable_autojudge(readiness)


def test_criteria_before_labels_is_out_of_order() -> None:
    """Criteria set while labels are not is out of order -> refused."""
    readiness = _readiness(False, True, False)
    assert can_enable_autojudge(readiness) is False
    with pytest.raises(Q11OrderError):
        enable_autojudge(readiness)


def test_precision_recall_before_criteria_is_out_of_order() -> None:
    """Precision/recall set while criteria are not is out of order -> refused.

    This is the exact reversal the Q11 discipline forbids: measuring the VLM before
    the criterion it is measured against exists.
    """
    readiness = _readiness(True, False, True)
    assert readiness.is_in_order() is False
    with pytest.raises(Q11OrderError):
        enable_autojudge(readiness)


def test_first_unmet_stage_reports_the_earliest_gap() -> None:
    """The refusal points at the earliest unmet stage, in order."""
    assert _readiness(False, False, False).first_unmet_stage() == "human_labels_collected"
    assert _readiness(True, False, False).first_unmet_stage() == "success_criteria_defined"
    assert _readiness(True, True, False).first_unmet_stage() == "precision_recall_measured"
    assert _readiness(True, True, True).first_unmet_stage() is None


def _functions_producing_enabled() -> set[str]:
    """Return the names of package functions that reference `AutoJudgeState.ENABLED`."""
    producers: set[str] = set()
    for source_path in _AUTOJUDGE_DIR.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr == "ENABLED"
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == "AutoJudgeState"
                ):
                    producers.add(node.name)
                    break
    return producers


def test_static_only_enable_autojudge_produces_the_enabled_state() -> None:
    """Static: `enable_autojudge` is the only function that yields ENABLED.

    Any other function reaching the enabled state would be a second enable path that
    bypasses the Q11 gate, so the scan must find exactly one producer.
    """
    assert _functions_producing_enabled() == {"enable_autojudge"}


def test_static_enable_autojudge_checks_order_and_completeness() -> None:
    """Static: the gate consults the ordering/completeness predicates before enabling."""
    source = inspect.getsource(enable_autojudge)
    assert "is_in_order" in source
    assert "first_unmet_stage" in source
