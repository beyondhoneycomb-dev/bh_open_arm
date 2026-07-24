"""The lineage recorder — assembles an eight-element record from upstream artifacts.

`02c` §1.5 SHAPE-CF: one owner for the schema (`record.py`), and two builders on top
of it — this recorder (the writer) and the query API (`store.py`). The recorder's
job is composition: it takes the pieces the upstream WPs already own and assembles
them into one `FR-TRN-054` snapshot, inventing nothing.

The three upstream reuses are load-bearing:

- element (a)'s `stats_hash` comes from WP-4A-04's `NormalizationContract`, not from a
  second hash computed here. `02c` §1.4 makes the stats content hash a single-owner
  canonicalisation; recomputing it would split the one rule and break stale
  propagation (CG-4A-05d), so the recorder takes the committed contract and reads its
  `stats_hash` off it.
- element (h) is WP-4A-03's `DegenerateDecision` list, passed through unchanged.
- elements (e)-(g) are the captured `VersionPins`, with the container digest already
  resolved to an explicit value (never absent).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.training.degenerate import DegenerateDecision
from backend.training.lineage.pins import VersionPins
from backend.training.lineage.record import (
    DatasetLineage,
    LineageRecord,
    MergeHistoryEntry,
    ObservationConfig,
)
from backend.training.lineage.store import CheckpointId, TrainingLineageStore
from backend.training.normstats import NormalizationContract


class LineageRecorder:
    """Builds `FR-TRN-054` snapshots from upstream artifacts and writes them.

    Ownership/threading: holds a `TrainingLineageStore` and writes through it; the
    store serialises concurrent writes, so a recorder may be shared across the
    threads that finalise runs.
    """

    def __init__(self, store: TrainingLineageStore) -> None:
        """Bind the recorder to the store it writes through.

        Args:
            store: The lineage store that persists the snapshot and reverse index.
        """
        self.mStore = store

    @staticmethod
    def build_record(
        repo_id: str,
        revision: str,
        info_hash: str,
        normalization_contract: NormalizationContract,
        observation: ObservationConfig,
        merge_history: Sequence[MergeHistoryEntry],
        train_config: Mapping[str, Any],
        pins: VersionPins,
        degenerate_decisions: Sequence[DegenerateDecision],
    ) -> LineageRecord:
        """Assemble one eight-element record, taking `stats_hash` from the contract.

        A static builder: assembly needs no store, so a caller can build a record for
        inspection before deciding to write it.

        Args:
            repo_id: The dataset's stamped `repo_id` (element (a)).
            revision: The dataset git revision (element (a)).
            info_hash: The `info.json` content hash (element (a)).
            normalization_contract: WP-4A-04's contract; its `stats_hash` is element
                (a)'s `stats.json` hash — reused, not recomputed.
            observation: The observation config (element (b)).
            merge_history: The per-source merge history (element (c)).
            train_config: The FULL `train_config.json` (element (d)).
            pins: The captured version pins (elements (e)-(g)).
            degenerate_decisions: WP-4A-03's decisions (element (h)); may be empty.

        Returns:
            (LineageRecord) The assembled record — not yet validated or written.
        """
        return LineageRecord(
            dataset=DatasetLineage(
                repo_id=repo_id,
                revision=revision,
                info_hash=info_hash,
                stats_hash=normalization_contract.stats_hash,
            ),
            observation=observation,
            merge_history=tuple(merge_history),
            train_config=train_config,
            pins=pins,
            degenerate_decisions=tuple(degenerate_decisions),
        )

    def record(
        self, record: LineageRecord, checkpoint: CheckpointId, dataset_content_hash: str
    ) -> None:
        """Validate and persist one assembled record to both composed stores.

        A thin pass-through to the store, kept on the recorder so a caller has one
        writer object for the whole build-then-record flow.

        Args:
            record: The assembled eight-element record.
            checkpoint: The checkpoint identity the snapshot attaches to.
            dataset_content_hash: The reverse-index content-hash key.

        Raises:
            LineageRecordError: When the record is missing an element.
            TrainingLineageError: When this checkpoint's lineage already exists.
        """
        self.mStore.record(record, checkpoint, dataset_content_hash)
