"""CG-4A-05d — a stats-hash change auto-marks descendant checkpoints and eval reports.

The propagation is automatic: its only input is the current statistics, and the
stale verdict is derived through WP-4A-04's committed hash contract, never by a
manual flag. A dataset whose statistics did not change carries no descendant into
the stale set.
"""

from __future__ import annotations

from backend.training.lineage import (
    CheckpointId,
    DatasetKey,
    StalePropagationEngine,
    TrainingLineageStore,
)
from tests.wp4a05.support import fit_stats, fixture_record, fixture_repo_id

_CONTENT_HASH = "content-hash-fixture"
_REVISION = "rev-0001"


def _key() -> DatasetKey:
    """The dataset key the fixture records are keyed under."""
    return DatasetKey(repo_id=fixture_repo_id(), revision=_REVISION)


def test_unchanged_stats_mark_nothing_stale(tmp_path) -> None:
    """The same statistics still hash to the recorded value — nothing is stale."""
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, _CONTENT_HASH)
        engine = StalePropagationEngine(store)
        report = engine.propagate({_key(): fit_stats()})
    assert not report.any_stale


def test_changed_stats_auto_mark_checkpoint_and_eval_report(tmp_path) -> None:
    """A new stats hash marks the descendant checkpoint AND its eval report stale.

    The only input to `propagate` is the changed statistics; no `set_stale` is called.
    """
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, _CONTENT_HASH)
        store.register_eval_report("eval-report-1", checkpoint)
        engine = StalePropagationEngine(store)
        # Statistics recomputed over a different frame count -> a different hash.
        changed = fit_stats(frames=17)
        report = engine.propagate({_key(): changed})
    assert report.stale_checkpoints == (checkpoint,)
    assert report.stale_eval_reports == ("eval-report-1",)


def test_only_the_changed_datasets_descendants_go_stale(tmp_path) -> None:
    """A stats change on one dataset does not stale a checkpoint of another dataset."""
    changed_checkpoint = CheckpointId("/runs/a", 1000)
    other_checkpoint = CheckpointId("/runs/b", 1000)
    other_repo = fixture_repo_id("openarm/other_task")
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), changed_checkpoint, _CONTENT_HASH)
        store.record(
            fixture_record(repo_id=other_repo, source_session=other_repo),
            other_checkpoint,
            "content-hash-other",
        )
        engine = StalePropagationEngine(store)
        report = engine.propagate({_key(): fit_stats(frames=17)})
    assert report.stale_checkpoints == (changed_checkpoint,)
    assert other_checkpoint not in report.stale_checkpoints


def test_is_stale_is_a_pure_derivation(tmp_path) -> None:
    """`is_stale` is a function of the record and current stats — no stored flag."""
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, _CONTENT_HASH)
        engine = StalePropagationEngine(store)
        record = store.snapshot_of(checkpoint)
        assert record is not None
        assert engine.is_stale(record, fit_stats(frames=17)) is True
        assert engine.is_stale(record, fit_stats()) is False


def test_a_dataset_absent_from_current_stats_is_not_evaluated(tmp_path) -> None:
    """A dataset whose current stats are not supplied is left unjudged, not stale."""
    checkpoint = CheckpointId("/runs/a", 1000)
    with TrainingLineageStore(tmp_path) as store:
        store.record(fixture_record(), checkpoint, _CONTENT_HASH)
        engine = StalePropagationEngine(store)
        report = engine.propagate({})
    assert not report.any_stale
