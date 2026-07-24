"""Automatic stale propagation across lineage — the §0.4 stats axis (CG-4A-05d).

`02c` §1.5 ④: a stats-hash change marks every descendant checkpoint and eval report
stale, and the acceptance is explicit that this is AUTOMATIC, not a manual flag. This
engine makes it automatic by deriving staleness rather than storing it: a checkpoint
is stale exactly when the statistics for its dataset no longer hash to the
`stats_hash` its lineage recorded. There is no `set_stale` — the only input is the
current statistics, and the verdict falls out of the hash comparison.

The comparison reuses the committed contract, not a local rule: element (a)'s
recorded `stats_hash` is wrapped in WP-4A-04's `NormalizationContract` and checked
with `contract_is_stale`, which defers to `backend.dataset.stats`'s single
canonicalisation. Two stale rules would split the propagation exactly as two hashing
rules would, so there is one, and it lives upstream.

An eval report descends from a checkpoint (the link recorded in the store), so a
stale checkpoint carries its eval reports into the stale set with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.stats.hashing import StatsInput
from backend.training.lineage.record import LineageRecord
from backend.training.lineage.store import CheckpointId, TrainingLineageStore
from backend.training.normstats import NormalizationContract, contract_is_stale


@dataclass(frozen=True)
class DatasetKey:
    """The identity a dataset's current statistics are looked up by.

    Statistics belong to a dataset version, identified by its stamped `repo_id` and
    git revision — the two element (a) fields that fix the version. Every checkpoint
    trained on that version shares this key, so one stats change reaches all of them.

    Attributes:
        repo_id: The dataset's stamped `repo_id`.
        revision: The dataset git revision.
    """

    repo_id: str
    revision: str


@dataclass(frozen=True)
class StaleReport:
    """The descendants a stats change marked stale (CG-4A-05d).

    Attributes:
        stale_checkpoints: Checkpoints whose recorded `stats_hash` no longer matches
            the current statistics for their dataset.
        stale_eval_reports: Eval reports descending from those checkpoints.
    """

    stale_checkpoints: tuple[CheckpointId, ...]
    stale_eval_reports: tuple[str, ...]

    @property
    def any_stale(self) -> bool:
        """Whether the change marked anything stale."""
        return bool(self.stale_checkpoints or self.stale_eval_reports)


class StalePropagationEngine:
    """Derives the stale descendants of a stats-hash change, never storing a flag."""

    def __init__(self, store: TrainingLineageStore) -> None:
        """Bind the engine to the store whose snapshots it reads.

        Args:
            store: The lineage store holding the eight-element snapshots and the
                eval-report descendant links.
        """
        self.mStore = store

    def is_stale(self, record: LineageRecord, current_stats: StatsInput) -> bool:
        """Report whether one record's dataset statistics have changed under it.

        Wraps the recorded `stats_hash` in a `NormalizationContract` and asks the
        committed `contract_is_stale` — so the staleness verdict uses WP-4A-04's one
        canonical hash rule, not a comparison invented here.

        Args:
            record: The lineage record whose recorded `stats_hash` is checked.
            current_stats: The statistics for that dataset as they stand now.

        Returns:
            (bool) True when the current statistics no longer hash to the recorded
                `stats_hash` — the checkpoint is stale.
        """
        contract = NormalizationContract(stats_hash=record.dataset.stats_hash)
        return contract_is_stale(contract, current_stats)

    def propagate(self, current_stats: dict[DatasetKey, StatsInput]) -> StaleReport:
        """Return every descendant a stats change marked stale — automatically.

        For each stored snapshot whose dataset appears in `current_stats`, the engine
        recomputes staleness from the hash comparison; a stale checkpoint pulls its
        descendant eval reports into the report with it. Nothing is written and no
        flag is set: the report is a pure function of the snapshots and the supplied
        current statistics, which is what makes the marking automatic (CG-4A-05d).

        Args:
            current_stats: The current statistics per dataset version. A dataset not
                present here is not evaluated — its statistics are simply unknown, not
                assumed unchanged or changed.

        Returns:
            (StaleReport) The stale checkpoints and their descendant eval reports.
        """
        stale_checkpoints: list[CheckpointId] = []
        stale_eval_reports: set[str] = set()
        for checkpoint, record in self.mStore.all_snapshots().items():
            key = DatasetKey(repo_id=record.dataset.repo_id, revision=record.dataset.revision)
            current = current_stats.get(key)
            if current is None:
                continue
            if not self.is_stale(record, current):
                continue
            stale_checkpoints.append(checkpoint)
            stale_eval_reports.update(self.mStore.eval_reports_of(checkpoint))
        stale_checkpoints.sort(key=lambda cp: (cp.output_dir, cp.step))
        return StaleReport(
            stale_checkpoints=tuple(stale_checkpoints),
            stale_eval_reports=tuple(sorted(stale_eval_reports)),
        )
