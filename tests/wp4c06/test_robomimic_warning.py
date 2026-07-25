"""CG-4C-06b — the robomimic warning is shown ALWAYS on every selection surface.

`FR-GUI-125` / `FR-INF-062`: offline metrics do not predict online success, and the
warning is unconditional — stamped first on the scorecard, the table, and the
selection result, carrying the robomimic study's own "50 to 100% worse" figure.
"""

from __future__ import annotations

from backend.eval.selection import CONDITION_NOMINAL, ROBOMIMIC_WARNING
from tests.wp4c06 import support

_ROBOMIMIC_FIGURE = "50 to 100%"


def test_scorecard_render_stamps_warning_first() -> None:
    """Every scorecard render leads with the robomimic warning (CG-4C-06b)."""
    text = support.scorecard(support.checkpoint(), 18, 20).render()
    assert text.splitlines()[0] == ROBOMIMIC_WARNING
    assert _ROBOMIMIC_FIGURE in text


def test_table_render_stamps_warning_first() -> None:
    """The accumulation table render leads with the warning."""
    table = support.table_of(support.scorecard(support.checkpoint(), 18, 20))
    text = table.render_table(CONDITION_NOMINAL)
    assert text.splitlines()[0] == ROBOMIMIC_WARNING


def test_selection_result_render_stamps_warning_first() -> None:
    """A selection result render leads with the warning, whatever the verdict."""
    a = support.checkpoint("/runs/A", 1000)
    b = support.checkpoint("/runs/B", 1000)
    table = support.table_of(
        support.scorecard(a, 38, 40, seed0=0),
        support.scorecard(a, 38, 40, seed0=40),
        support.scorecard(b, 10, 40, seed0=1000),
        support.scorecard(b, 10, 40, seed0=1040),
    )
    text = table.select_for_task(support.DEFAULT_TASK, CONDITION_NOMINAL).render()
    assert text.splitlines()[0] == ROBOMIMIC_WARNING
    assert _ROBOMIMIC_FIGURE in text


def test_warning_names_offline_metrics_do_not_predict() -> None:
    """The warning states the substantive claim, not just a citation."""
    assert "온라인 성공률을 예측하지 못한다" in ROBOMIMIC_WARNING
