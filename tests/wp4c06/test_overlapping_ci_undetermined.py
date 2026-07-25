"""CG-4C-06d — two checkpoints with overlapping Wilson CIs give 'undetermined'.

`02c` §3.6: selection is an interval comparison, not a point-estimate one, and it
delegates to the committed WP-4C-03 `compare_checkpoints`. A forced rank is never an
output: overlapping intervals, single runs, and sub-threshold samples all collapse
to UNDETERMINED with no selected checkpoint.
"""

from __future__ import annotations

from backend.eval.selection import (
    CONDITION_NOMINAL,
    SELECTION_NO_CANDIDATES,
    SELECTION_SELECTED,
    SELECTION_SOLE_CANDIDATE,
    SELECTION_UNDETERMINED,
)
from backend.eval.stats.constants import (
    REASON_NOT_MEANINGFUL,
    REASON_OVERLAPPING_CI,
    REASON_SINGLE_RUN,
)
from tests.wp4c06 import support

_A = support.checkpoint("/runs/A", 1000)
_B = support.checkpoint("/runs/B", 1000)


def test_overlapping_cis_are_undetermined() -> None:
    """0.55 vs 0.50 at N=40 each (two runs) overlap -> UNDETERMINED, no rank (CG-4C-06d)."""
    table = support.table_of(
        support.scorecard(_A, 22, 40, seed0=0),
        support.scorecard(_A, 22, 40, seed0=40),
        support.scorecard(_B, 20, 40, seed0=1000),
        support.scorecard(_B, 20, 40, seed0=1040),
    )
    result = table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)
    assert result.verdict == SELECTION_UNDETERMINED
    assert result.selected is None
    assert any(c.reason == REASON_OVERLAPPING_CI for c in result.comparisons)


def test_disjoint_cis_select_the_separated_leader() -> None:
    """0.95 vs 0.25 at N=40 each separate -> the leader is SELECTED."""
    table = support.table_of(
        support.scorecard(_A, 38, 40, seed0=0),
        support.scorecard(_A, 38, 40, seed0=40),
        support.scorecard(_B, 10, 40, seed0=1000),
        support.scorecard(_B, 10, 40, seed0=1040),
    )
    result = table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)
    assert result.verdict == SELECTION_SELECTED
    assert result.selected == _A


def test_single_run_per_checkpoint_is_undetermined() -> None:
    """One run per side cannot be ranked (FR-INF-063) -> UNDETERMINED."""
    table = support.table_of(
        support.scorecard(_A, 38, 40, seed0=0),
        support.scorecard(_B, 10, 40, seed0=1000),
    )
    result = table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)
    assert result.verdict == SELECTION_UNDETERMINED
    assert result.selected is None
    assert any(c.reason == REASON_SINGLE_RUN for c in result.comparisons)


def test_sub_threshold_samples_are_undetermined() -> None:
    """Two runs each but N=10 (< 20) -> not meaningful -> UNDETERMINED."""
    table = support.table_of(
        support.scorecard(_A, 9, 10, seed0=0),
        support.scorecard(_A, 9, 10, seed0=10),
        support.scorecard(_B, 2, 10, seed0=1000),
        support.scorecard(_B, 2, 10, seed0=1010),
    )
    result = table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)
    assert result.verdict == SELECTION_UNDETERMINED
    assert result.selected is None
    assert any(c.reason == REASON_NOT_MEANINGFUL for c in result.comparisons)


def test_sole_candidate_and_no_candidate() -> None:
    """One checkpoint is a sole candidate; an unknown (task, condition) has none."""
    table = support.table_of(support.scorecard(_A, 38, 40, seed0=0))
    sole = table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL)
    assert sole.verdict == SELECTION_SOLE_CANDIDATE
    assert sole.selected == _A

    none = table.select_for_task("unknown-task", CONDITION_NOMINAL)
    assert none.verdict == SELECTION_NO_CANDIDATES
    assert none.selected is None
