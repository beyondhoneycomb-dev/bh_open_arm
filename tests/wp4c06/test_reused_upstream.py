"""DO-NOT-DUPLICATE — WP-4C-06 reuses the committed contracts, redefining none.

`02c` §3.6: WP-4C-06 imports the committed WP-4C-03 `SuccessRateReport` /
`compare_checkpoints` and WP-4A-05 lineage, and consumes the condition as a generic
value — NOT WP-4C-05's enum (a data-join, so the three build in parallel with no type
dependency). This test pins those reuse facts by identity.
"""

from __future__ import annotations

import backend.eval.selection.table as table_module
from backend.eval.selection import CONDITION_NOMINAL, PerTaskReport
from backend.eval.stats import SuccessRateReport as StatsReport
from backend.eval.stats import compare_checkpoints as stats_compare
from backend.training.lineage import CheckpointId as LineageCheckpointId
from tests.wp4c06 import support


def test_compare_checkpoints_is_the_committed_one() -> None:
    """Selection uses WP-4C-03's `compare_checkpoints`, not a private reimplementation."""
    assert table_module.compare_checkpoints is stats_compare


def test_scorecard_is_keyed_by_lineage_checkpoint_id() -> None:
    """A scorecard's checkpoint is the WP-4A-05 lineage identity type."""
    card = support.scorecard(support.checkpoint(), 18, 20)
    assert isinstance(card.checkpoint, LineageCheckpointId)


def test_per_task_report_is_the_committed_success_rate_report() -> None:
    """Each per-task report is WP-4C-03's `SuccessRateReport`, imported unchanged."""
    card = support.scorecard(support.checkpoint(), 18, 20)
    assert isinstance(card.per_task[0].report, StatsReport)


def test_condition_is_a_generic_string_value() -> None:
    """The condition is joined by value; an arbitrary string is accepted, no enum."""
    report = support.report(support.checkpoint(), 18, 20)
    entry = PerTaskReport("pick", "SOME_FUTURE_CONDITION", report)
    assert isinstance(entry.condition, str)
    assert isinstance(CONDITION_NOMINAL, str)


def test_selection_package_defines_no_condition_enum() -> None:
    """WP-4C-06 owns no `Condition` type — WP-4C-05 does (`02c` §3.6 DO-NOT-DUPLICATE)."""
    import backend.eval.selection as selection

    assert not hasattr(selection, "Condition")
