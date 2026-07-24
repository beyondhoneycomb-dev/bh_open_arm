"""WP-4A-05 — the `FR-TRN-054` lineage record and the bidirectional query (`02c` §1.5).

`FR-TRN-054` fixes an immutable eight-element snapshot of one checkpoint-producing
run — (a) dataset identity, (b) observation config, (c) session merge history,
(d) the full `train_config.json`, (e) training-code git SHA, (f) LeRobot version,
(g) container image digest, (h) degenerate-channel decisions. The interface contract
is 1:1 with those eight: this package invents no field and omits none, and a record
missing any element BLOCKs (CG-4A-05a) — including (g), whose not-used case is a
recorded value, never an absent field.

This band builds ON committed upstream, not beside it:

- the bidirectional query (`FR-OPS-070`) composes WP-3D-04's reverse index
  (`backend.dataset.lineage`) — `checkpoints_of` / `episodes_of` adapt its shape into
  the episode-set form, and the pre-delete guard (`FR-DAT-008`, CG-4A-05e) delegates
  to its referencing query. No second reverse index is built.
- element (a)'s `stats_hash` is WP-4A-04's committed `NormalizationContract` hash, and
  stale propagation (CG-4A-05d) is derived through that same contract — one stats
  canonicalisation, one stale rule (`02c` §1.4 SHAPE-CF).
- element (h) is WP-4A-03's `DegenerateDecision`, imported unchanged.

The snapshot itself is immutable: a checkpoint's lineage is written once and any
later edit is refused (CG-4A-05b).
"""

from __future__ import annotations

from backend.training.lineage.constants import CONTAINER_NOT_USED
from backend.training.lineage.pins import (
    LineagePinError,
    VersionPins,
    capture_version_pins,
    git_head_sha,
    installed_lerobot_version,
)
from backend.training.lineage.record import (
    DatasetLineage,
    LineageRecord,
    LineageRecordError,
    MergeHistoryEntry,
    ObservationConfig,
)
from backend.training.lineage.recorder import LineageRecorder
from backend.training.lineage.stale import (
    DatasetKey,
    StalePropagationEngine,
    StaleReport,
)
from backend.training.lineage.store import (
    CheckpointId,
    EpisodeRef,
    TrainingLineageError,
    TrainingLineageStore,
)

__all__ = [
    "CONTAINER_NOT_USED",
    "CheckpointId",
    "DatasetKey",
    "DatasetLineage",
    "EpisodeRef",
    "LineagePinError",
    "LineageRecord",
    "LineageRecordError",
    "LineageRecorder",
    "MergeHistoryEntry",
    "ObservationConfig",
    "StalePropagationEngine",
    "StaleReport",
    "TrainingLineageError",
    "TrainingLineageStore",
    "VersionPins",
    "capture_version_pins",
    "git_head_sha",
    "installed_lerobot_version",
]
