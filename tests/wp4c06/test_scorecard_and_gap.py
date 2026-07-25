"""Scorecard structure and the DERIVED generalization gap (`02c` §3.5 / §3.6).

The scorecard refuses structurally unsound rows, and the generalization gap is
`nominal − perturbed` with NO separate confidence interval; with PERTURBED deferred
it is unmeasured and the report says so rather than emitting a fabricated 0.
"""

from __future__ import annotations

import pytest

from backend.eval.selection import (
    CONDITION_NOMINAL,
    CONDITION_PERTURBED,
    GENERALIZATION_GAP_UNMEASURED,
    CheckpointScorecard,
    CheckpointScorecardError,
    PerTaskReport,
)
from tests.wp4c06 import support


def test_nominal_only_gap_is_unmeasured() -> None:
    """With PERTURBED deferred, the gap is None and the render says 'unmeasured' (§3.5)."""
    card = support.scorecard(support.checkpoint(), 18, 20, condition=CONDITION_NOMINAL)
    assert card.generalization_gap(support.DEFAULT_TASK) is None
    assert GENERALIZATION_GAP_UNMEASURED in card.render()


def test_gap_is_derived_when_both_conditions_present() -> None:
    """When both conditions exist, the gap is nominal − perturbed, a derived value."""
    ckpt = support.checkpoint()
    nominal = support.report(ckpt, 18, 20, seed0=0)
    perturbed = support.report(ckpt, 12, 20, seed0=100)
    card = CheckpointScorecard(
        checkpoint=ckpt,
        lineage_ref="/runs/a@1000",
        per_task=(
            PerTaskReport(support.DEFAULT_TASK, CONDITION_NOMINAL, nominal),
            PerTaskReport(support.DEFAULT_TASK, CONDITION_PERTURBED, perturbed),
        ),
        offline_metrics=support.DEFAULT_METRICS,
        frequencies=support.DEFAULT_FREQ,
    )
    card.validate()
    gap = card.generalization_gap(support.DEFAULT_TASK)
    assert gap == pytest.approx(0.9 - 0.6)


def test_empty_per_task_is_refused() -> None:
    """A scorecard with no success rate is not a selection basis."""
    with pytest.raises(CheckpointScorecardError):
        CheckpointScorecard(
            checkpoint=support.checkpoint(),
            lineage_ref="/runs/a@1000",
            per_task=(),
            offline_metrics=support.DEFAULT_METRICS,
            frequencies=support.DEFAULT_FREQ,
        ).validate()


def test_empty_lineage_ref_is_refused() -> None:
    """A selection row must trace to WP-4A-05 lineage."""
    ckpt = support.checkpoint()
    with pytest.raises(CheckpointScorecardError):
        CheckpointScorecard(
            checkpoint=ckpt,
            lineage_ref="  ",
            per_task=(
                PerTaskReport(
                    support.DEFAULT_TASK, CONDITION_NOMINAL, support.report(ckpt, 18, 20)
                ),
            ),
            offline_metrics=support.DEFAULT_METRICS,
            frequencies=support.DEFAULT_FREQ,
        ).validate()


def test_report_for_a_foreign_checkpoint_is_refused() -> None:
    """A scorecard cannot carry another checkpoint's report (it would pool foreign trials)."""
    ckpt = support.checkpoint("/runs/a", 1000)
    other = support.checkpoint("/runs/b", 2000)
    with pytest.raises(CheckpointScorecardError):
        CheckpointScorecard(
            checkpoint=ckpt,
            lineage_ref="/runs/a@1000",
            per_task=(
                PerTaskReport(
                    support.DEFAULT_TASK, CONDITION_NOMINAL, support.report(other, 18, 20)
                ),
            ),
            offline_metrics=support.DEFAULT_METRICS,
            frequencies=support.DEFAULT_FREQ,
        ).validate()


def test_duplicate_task_condition_is_refused() -> None:
    """One report per (task, condition)."""
    ckpt = support.checkpoint()
    entry = PerTaskReport(support.DEFAULT_TASK, CONDITION_NOMINAL, support.report(ckpt, 18, 20))
    with pytest.raises(CheckpointScorecardError):
        CheckpointScorecard(
            checkpoint=ckpt,
            lineage_ref="/runs/a@1000",
            per_task=(entry, entry),
            offline_metrics=support.DEFAULT_METRICS,
            frequencies=support.DEFAULT_FREQ,
        ).validate()
