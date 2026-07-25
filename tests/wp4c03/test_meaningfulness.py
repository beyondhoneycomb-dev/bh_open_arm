"""CG-4C-03c — N<20 is flagged statistically meaningless and yields no ranking.

`NFR-PRF-050`/`FR-SIM-056`: N>=20 is the only basis of meaningfulness, and a
comparison touching a sub-threshold run must print "통계적으로 무의미" and issue no
superiority verdict.
"""

from __future__ import annotations

from backend.eval.stats import (
    N_MIN_MEANINGFUL,
    VERDICT_UNDETERMINED,
    compare_checkpoints,
)
from backend.eval.stats.constants import (
    REASON_NOT_MEANINGFUL,
    STATISTICALLY_MEANINGLESS_LABEL,
)
from tests.wp4c03.support import checkpoint, report

_SUB_THRESHOLD_N = N_MIN_MEANINGFUL - 1


def test_below_threshold_not_meaningful() -> None:
    """A report with N<20 is flagged not statistically meaningful."""
    assert report(n_success=9, n_trials=_SUB_THRESHOLD_N).statistically_meaningful is False


def test_at_threshold_is_meaningful() -> None:
    """Exactly N=20 clears the bar — the threshold is the only basis, and it is >=."""
    assert report(n_success=10, n_trials=N_MIN_MEANINGFUL).statistically_meaningful is True


def test_render_marks_meaningless_below_threshold() -> None:
    """The rendered report carries the meaningless label below N=20 (CG-4C-03c)."""
    rendered = report(n_success=9, n_trials=_SUB_THRESHOLD_N).render()
    assert STATISTICALLY_MEANINGLESS_LABEL in rendered


def test_render_omits_meaningless_at_threshold() -> None:
    """A meaningful report does not carry the meaningless label."""
    rendered = report(n_success=10, n_trials=N_MIN_MEANINGFUL).render()
    assert STATISTICALLY_MEANINGLESS_LABEL not in rendered


def test_comparison_with_subthreshold_run_is_undetermined() -> None:
    """CG-4C-03c: comparing a checkpoint with an N<20 run yields no ranking."""
    ck_a = checkpoint("/runs/a", 1000)
    ck_b = checkpoint("/runs/b", 1000)
    # Enough runs per side (clears the single-run guard) but each is sub-threshold,
    # so the meaningfulness guard is what must bite here.
    runs_a = [report(9, _SUB_THRESHOLD_N, "/runs/a"), report(9, _SUB_THRESHOLD_N, "/runs/a")]
    runs_b = [report(1, _SUB_THRESHOLD_N, "/runs/b"), report(1, _SUB_THRESHOLD_N, "/runs/b")]
    result = compare_checkpoints(runs_a, runs_b)
    assert result.verdict == VERDICT_UNDETERMINED
    assert result.reason == REASON_NOT_MEANINGFUL
    assert result.is_ranked is False
    assert {result.checkpoint_a, result.checkpoint_b} == {ck_a, ck_b}
