"""Reverse dataset/episode lineage (WP-3D-04).

LeRobot restores lineage forward only — from a `train_config.json` it rebuilds the
dataset and episodes a run consumed. The reverse question, "which checkpoints used
this episode", it never answers, so this package keeps the inverted index that does
(`02b` §8.2 WP-3D-04). A record ties one checkpoint (`output_dir` + step) to the
dataset it trained on (stamped `repo_id`, content hash, revision), the episodes it
consumed, the normalisation stats hash, and the exact channel-selection state — and
the store answers the reverse query, reproduces the channel state, and warns before
a dataset delete would orphan a checkpoint's lineage.

The dataset-source identity reuses the recorder's `repo_id` rules (WP-3B-11) rather
than forking them, and the channel/state semantics come from `CTR-REC@v1`
(`contracts.recorder`); this package redefines neither.
"""

from __future__ import annotations

from backend.dataset.lineage.channels import ChannelSelection, ChannelSelectionError
from backend.dataset.lineage.record import LineageError, LineageRecord
from backend.dataset.lineage.source import (
    LineageSourceError,
    is_stamped_repo_id,
    validate_dataset_repo_id,
)
from backend.dataset.lineage.store import (
    CheckpointRef,
    DeleteGuard,
    LineageStore,
)

__all__ = [
    "ChannelSelection",
    "ChannelSelectionError",
    "CheckpointRef",
    "DeleteGuard",
    "LineageError",
    "LineageRecord",
    "LineageSourceError",
    "LineageStore",
    "is_stamped_repo_id",
    "validate_dataset_repo_id",
]
