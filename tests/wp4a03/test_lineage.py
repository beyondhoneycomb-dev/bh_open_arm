"""CG-4A-03e — the three-way decision is queryable in lineage (`FR-TRN-054` (h)).

The decision recorded by the gate must be retrievable from the immutable lineage
slice, and a second write for the same run must be refused (the snapshot is
immutable). Recording an empty decision set is a positive statement that degeneracy
was checked and none was found — also queryable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.training.degenerate import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
    DegenerateLineageStore,
    NormMode,
)
from backend.training.preflight import Component


def _decision() -> DegenerateDecision:
    finding = DegenerateFinding(
        channel_name="left_joint_3.torque",
        joint="left_joint_3",
        component=Component.TORQUE,
        norm_mode=NormMode.QUANTILES,
        statistic=0.0,
        threshold=1e-4,
        amplification_estimate=1e8,
    )
    return DegenerateDecision(
        finding, DegenerateChoice.EXCLUDE, "non-contact span, exclude channel"
    )


def test_cg_4a_03e_decision_round_trips_through_lineage(tmp_path: Path) -> None:
    store = DegenerateLineageStore(tmp_path / "degenerate_lineage.json")
    decision = _decision()

    store.record("run-1", (decision,))
    got = store.decisions_of("run-1")

    assert got is not None
    assert got == (decision,)
    # The choice — and the channel it was made about — are both queryable.
    assert got[0].choice is DegenerateChoice.EXCLUDE
    assert got[0].finding.channel_name == "left_joint_3.torque"
    assert got[0].finding.component is Component.TORQUE
    assert got[0].finding.norm_mode is NormMode.QUANTILES


def test_absent_run_returns_none(tmp_path: Path) -> None:
    store = DegenerateLineageStore(tmp_path / "degenerate_lineage.json")
    assert store.decisions_of("never-recorded") is None


def test_lineage_is_immutable_second_write_refused(tmp_path: Path) -> None:
    store = DegenerateLineageStore(tmp_path / "degenerate_lineage.json")
    store.record("run-1", (_decision(),))
    with pytest.raises(ValueError, match="immutable"):
        store.record("run-1", (_decision(),))


def test_empty_decision_set_is_recorded_and_queryable(tmp_path: Path) -> None:
    # A clean dataset: degeneracy was checked, none found — recording the empty set
    # is a positive statement, distinct from "never checked" (which returns None).
    store = DegenerateLineageStore(tmp_path / "degenerate_lineage.json")
    store.record("run-clean", ())
    assert store.decisions_of("run-clean") == ()
    assert store.decisions_of("run-missing") is None


def test_lineage_survives_a_new_store_instance(tmp_path: Path) -> None:
    # Persistence is on disk, so a fresh store over the same file reads the record —
    # lineage outlives the process that wrote it.
    path = tmp_path / "degenerate_lineage.json"
    DegenerateLineageStore(path).record("run-1", (_decision(),))
    reopened = DegenerateLineageStore(path)
    assert reopened.decisions_of("run-1") == (_decision(),)
