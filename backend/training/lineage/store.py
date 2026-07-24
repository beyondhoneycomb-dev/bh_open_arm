"""The lineage store: immutable snapshots composed with WP-3D-04's reverse index.

`02c` §1.5 produces three things this module carries: the `index.sqlite`
bidirectional index, the recorder's persistence, and the substrate the stale engine
reads. The bidirectional index is NOT rebuilt here — WP-3D-04
(`backend.dataset.lineage`) already keeps the episode->checkpoint reverse index that
LeRobot never does, and the load-bearing rule of this WP is to reuse it, not fork a
second one. So this store COMPOSES a `LineageStore`: the reverse query, the forward
read-back and the pre-delete reference query all delegate to it, and the query API
`checkpoints_of` / `episodes_of` is a thin adaptation of its shape into the
episode-set form `FR-OPS-070` asks for.

What this store adds on top is the eight-element `FR-TRN-054` snapshot the reverse
index does not hold: a JSON file, one immutable record per checkpoint, refusing any
overwrite so a recorded lineage cannot be edited after the fact (CG-4A-05b). It also
keeps the eval-report -> checkpoint descendant links the stale engine propagates
through (CG-4A-05d).

Ownership/threading: one instance owns one reverse-index connection for its
lifetime; open it as a context manager or call `close()`. The JSON snapshot file is
guarded by an internal lock, matching the sibling stores
(`orchestrator.job_lineage`, `degenerate.lineage`).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from backend.dataset.lineage import (
    ChannelSelection,
    CheckpointRef,
    DeleteGuard,
    LineageStore,
)
from backend.dataset.lineage import LineageRecord as ReverseLineageRecord
from backend.training.lineage.constants import (
    EVAL_REPORT_OUTPUT_DIR_KEY,
    EVAL_REPORT_STEP_KEY,
    EVAL_REPORTS_KEY,
    REVERSE_INDEX_FILENAME,
    SCHEMA_VERSION_KEY,
    SNAPSHOT_FILENAME,
    SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOTS_KEY,
)
from backend.training.lineage.record import LineageRecord
from contracts.recorder import POSITION_SUFFIX, TORQUE_SUFFIX, VELOCITY_SUFFIX


class TrainingLineageError(RuntimeError):
    """Raised on an immutability violation or an incoherent snapshot store.

    The `FAIL_BLOCKING` cases: a second write for a checkpoint whose lineage is
    already recorded (CG-4A-05b), an eval report re-linked to a different checkpoint,
    or a snapshot file whose generation this reader does not understand.
    """


@dataclass(frozen=True)
class CheckpointId:
    """A checkpoint's identity — its output directory and step.

    `output_dir` + step is the checkpoint identity everywhere in the lineage stores
    (WP-3D-04 and this one), so it is one value object rather than a loose pair.

    Attributes:
        output_dir: The training run's output directory.
        step: The checkpoint step within that run.
    """

    output_dir: str
    step: int


@dataclass(frozen=True)
class EpisodeRef:
    """An episode's identity for the bidirectional query.

    An episode is only identified within a dataset version, so its identity is the
    dataset content hash plus the index — the exact key WP-3D-04's reverse query
    takes (`checkpoints_for_episode`).

    Attributes:
        dataset_content_hash: The dataset version the episode belongs to.
        episode_index: The episode index within that dataset.
    """

    dataset_content_hash: str
    episode_index: int


class TrainingLineageStore:
    """Immutable eight-element snapshots plus the composed WP-3D-04 reverse index."""

    def __init__(self, base_dir: str | Path) -> None:
        """Open (creating if absent) the two composed stores under `base_dir`.

        Args:
            base_dir: The directory holding `index.sqlite` (the WP-3D-04 reverse
                index) and the snapshot JSON file.
        """
        self.mBaseDir = Path(base_dir)
        self.mBaseDir.mkdir(parents=True, exist_ok=True)
        self.mReverseIndex = LineageStore(self.mBaseDir / REVERSE_INDEX_FILENAME)
        self.mSnapshotPath = self.mBaseDir / SNAPSHOT_FILENAME
        self.mLock = threading.Lock()

    def __enter__(self) -> TrainingLineageStore:
        """Enter the runtime context, returning this store."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the composed reverse index on context exit."""
        self.close()

    def close(self) -> None:
        """Close the composed reverse-index connection. Idempotent."""
        self.mReverseIndex.close()

    def record(
        self, record: LineageRecord, checkpoint: CheckpointId, dataset_content_hash: str
    ) -> None:
        """Validate and store one run's lineage in both composed stores.

        The eight-element snapshot and the WP-3D-04 reverse-index record are written
        together. Everything is validated before anything is written, so a rejected
        record leaves neither store touched; the snapshot is written first (its
        immutability is this store's authority) and the reverse-index record second.
        A checkpoint whose lineage is already recorded is refused by both — a
        checkpoint's lineage is immutable (CG-4A-05b).

        Args:
            record: The eight-element `FR-TRN-054` snapshot.
            checkpoint: The checkpoint identity the snapshot attaches to.
            dataset_content_hash: The dataset version's content hash — the
                reverse-index key (WP-3D-03), not part of the snapshot itself.

        Raises:
            LineageRecordError: When the record is missing an element.
            LineageError: When the derived reverse-index record is inconsistent
                (unstamped `repo_id`, empty episodes, or a channel/width mismatch).
            TrainingLineageError: When this checkpoint's lineage already exists.
        """
        record.validate()
        reverse_entry = _reverse_record(record, checkpoint, dataset_content_hash)
        # Pre-validate the reverse record so a reject cannot land after the snapshot
        # is written; the store re-validates on `record()`, but doing it here keeps
        # the two writes all-or-nothing on the normal path.
        reverse_entry.validate()
        key = _checkpoint_key(checkpoint)
        with self.mLock:
            store = self._load()
            snapshots = store[SNAPSHOTS_KEY]
            if key in snapshots:
                raise TrainingLineageError(
                    f"lineage for checkpoint {checkpoint.output_dir}@{checkpoint.step} is already "
                    "recorded; a checkpoint's lineage is immutable"
                )
            snapshots[key] = record.to_dict()
            self._write(store)
            self.mReverseIndex.record(reverse_entry)

    def snapshot_of(self, checkpoint: CheckpointId) -> LineageRecord | None:
        """Read one checkpoint's eight-element snapshot back, or None when absent.

        Args:
            checkpoint: The checkpoint identity.

        Returns:
            (LineageRecord | None) The reconstructed record, or None.
        """
        with self.mLock:
            raw = self._load()[SNAPSHOTS_KEY].get(_checkpoint_key(checkpoint))
        return None if raw is None else LineageRecord.from_dict(raw)

    def all_snapshots(self) -> dict[CheckpointId, LineageRecord]:
        """Read every stored snapshot, keyed by checkpoint identity.

        The stale engine reads the whole set to find descendants of a changed stats
        hash; the read is a copy, so a caller cannot mutate the store through it.

        Returns:
            (dict[CheckpointId, LineageRecord]) Every stored record.
        """
        with self.mLock:
            snapshots = dict(self._load()[SNAPSHOTS_KEY])
        return {
            _key_to_checkpoint(key): LineageRecord.from_dict(raw) for key, raw in snapshots.items()
        }

    def checkpoints_of(self, episodes: Iterable[EpisodeRef]) -> tuple[CheckpointRef, ...]:
        """Return every checkpoint that trained on any episode in the set.

        The `FR-OPS-070` forward-of-reverse direction: composed from WP-3D-04's
        `checkpoints_for_episode`, unioned over the episode set and de-duplicated by
        checkpoint identity. This reuses the reverse index rather than deriving a
        second one.

        Args:
            episodes: The episodes to attribute checkpoints to.

        Returns:
            (tuple[CheckpointRef, ...]) Referencing checkpoints, ordered by
                `output_dir` then step; empty when none.
        """
        found: dict[tuple[str, int], CheckpointRef] = {}
        for episode in episodes:
            for ref in self.mReverseIndex.checkpoints_for_episode(
                episode.dataset_content_hash, episode.episode_index
            ):
                found[(ref.output_dir, ref.step)] = ref
        return tuple(sorted(found.values(), key=lambda ref: (ref.output_dir, ref.step)))

    def episodes_of(self, checkpoint: CheckpointId) -> tuple[EpisodeRef, ...]:
        """Return the episodes one checkpoint consumed, from the reverse index.

        Composed from WP-3D-04's forward read-back (`get`), whose record carries both
        the dataset content hash and the episode list — exactly the `EpisodeRef`
        identity. Empty when the checkpoint is not recorded.

        Args:
            checkpoint: The checkpoint identity.

        Returns:
            (tuple[EpisodeRef, ...]) The consumed episodes, ascending by index.
        """
        entry = self.mReverseIndex.get(checkpoint.output_dir, checkpoint.step)
        if entry is None:
            return ()
        return tuple(
            EpisodeRef(dataset_content_hash=entry.dataset_content_hash, episode_index=index)
            for index in entry.episodes
        )

    def guard_delete(self, dataset_content_hash: str) -> DeleteGuard:
        """Ask whether a dataset is safe to delete, reusing WP-3D-04's guard.

        `FR-DAT-008` requires a delete to list the referencing checkpoints and warn;
        WP-3D-04 already derives that referencing set, so this delegates rather than
        re-deriving it (CG-4A-05e). A one-directional lineage could not answer this,
        which is why the query is bidirectional (`02c` §1.5 negative branch).

        Args:
            dataset_content_hash: The dataset version the caller intends to delete.

        Returns:
            (DeleteGuard) The referencing checkpoints and a `safe` verdict.
        """
        return self.mReverseIndex.guard_delete(dataset_content_hash)

    def register_eval_report(self, report_id: str, checkpoint: CheckpointId) -> None:
        """Link an eval report to the checkpoint it was produced from.

        The stale engine propagates a stats-hash change from a checkpoint to its
        descendant eval reports (CG-4A-05d); this records that descendant edge. A
        report belongs to exactly one checkpoint, so re-linking it to a different one
        is refused.

        Args:
            report_id: The eval report's identity.
            checkpoint: The checkpoint it descends from.

        Raises:
            TrainingLineageError: When the report is already linked to another
                checkpoint.
        """
        with self.mLock:
            store = self._load()
            reports = store[EVAL_REPORTS_KEY]
            existing = reports.get(report_id)
            link = {
                EVAL_REPORT_OUTPUT_DIR_KEY: checkpoint.output_dir,
                EVAL_REPORT_STEP_KEY: checkpoint.step,
            }
            if existing is not None and existing != link:
                raise TrainingLineageError(
                    f"eval report {report_id!r} is already linked to a different checkpoint; "
                    "an eval report descends from exactly one checkpoint"
                )
            reports[report_id] = link
            self._write(store)

    def eval_reports_of(self, checkpoint: CheckpointId) -> tuple[str, ...]:
        """Return the eval reports that descend from one checkpoint.

        Args:
            checkpoint: The checkpoint identity.

        Returns:
            (tuple[str, ...]) The descendant eval-report ids, sorted; empty when none.
        """
        with self.mLock:
            reports = dict(self._load()[EVAL_REPORTS_KEY])
        return tuple(
            sorted(
                report_id
                for report_id, link in reports.items()
                if link.get(EVAL_REPORT_OUTPUT_DIR_KEY) == checkpoint.output_dir
                and int(link.get(EVAL_REPORT_STEP_KEY, -1)) == checkpoint.step
            )
        )

    def _load(self) -> dict[str, Any]:
        """Read the snapshot file, or an empty two-map store when absent.

        Raises:
            TrainingLineageError: When an existing file's generation is not this one.
        """
        if not self.mSnapshotPath.is_file():
            return {
                SCHEMA_VERSION_KEY: SNAPSHOT_SCHEMA_VERSION,
                SNAPSHOTS_KEY: {},
                EVAL_REPORTS_KEY: {},
            }
        loaded: dict[str, Any] = json.loads(self.mSnapshotPath.read_text(encoding="utf-8"))
        stored_version = loaded.get(SCHEMA_VERSION_KEY)
        if stored_version != SNAPSHOT_SCHEMA_VERSION:
            raise TrainingLineageError(
                f"snapshot store at {self.mSnapshotPath} is generation {stored_version}, expected "
                f"{SNAPSHOT_SCHEMA_VERSION}; refusing to misread an incompatible generation"
            )
        loaded.setdefault(SNAPSHOTS_KEY, {})
        loaded.setdefault(EVAL_REPORTS_KEY, {})
        return loaded

    def _write(self, store: dict[str, Any]) -> None:
        """Write the whole snapshot store back deterministically."""
        store[SCHEMA_VERSION_KEY] = SNAPSHOT_SCHEMA_VERSION
        self.mSnapshotPath.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")


def _checkpoint_key(checkpoint: CheckpointId) -> str:
    """Encode a checkpoint identity as a stable JSON map key."""
    return json.dumps([checkpoint.output_dir, checkpoint.step], sort_keys=True)


def _key_to_checkpoint(key: str) -> CheckpointId:
    """Decode a checkpoint map key back into its identity."""
    output_dir, step = json.loads(key)
    return CheckpointId(output_dir=str(output_dir), step=int(step))


def _reverse_record(
    record: LineageRecord, checkpoint: CheckpointId, dataset_content_hash: str
) -> ReverseLineageRecord:
    """Build the WP-3D-04 reverse-index record from the eight-element snapshot.

    The reverse index needs its own fields (a content-hash key, a `ChannelSelection`,
    an episode list); each is derived from the snapshot rather than stored twice. The
    episode list is the union of element (c)'s maps (`consumed_episodes`), and the
    channel selection is read off the observation names — so the reverse record is a
    projection of the snapshot, not a parallel source of truth.

    Encoder settings are outside the `FR-TRN-054` snapshot, so the reverse record
    carries an empty encoder map: this composition uses the reverse index only for
    the episode and delete-guard axes, which the encoder settings do not affect.
    """
    return ReverseLineageRecord(
        repo_id=record.dataset.repo_id,
        dataset_content_hash=dataset_content_hash,
        revision=record.dataset.revision,
        episodes=record.consumed_episodes(),
        stats_hash=record.dataset.stats_hash,
        use_velocity_and_torque=record.observation.use_velocity_and_torque,
        state_dim=record.observation.state_shape,
        encoder_settings={},
        channels=_channels_from_names(record.observation.names),
        output_dir=checkpoint.output_dir,
        step=checkpoint.step,
    )


def _channels_from_names(names: tuple[str, ...]) -> ChannelSelection:
    """Derive the WP-3D-04 `ChannelSelection` from the observation state names.

    The per-motor suffixes come from `CTR-REC@v1` (`contracts.recorder`), so a
    channel decision here cannot drift from the recorder grammar. Depth is an image
    channel, not a state name, so it is absent from this list and recorded False —
    the state vector is fully reproducible from the names; depth-image selection is
    outside the `FR-TRN-054` (b) state-name scope.
    """
    return ChannelSelection(
        pos=any(name.endswith(POSITION_SUFFIX) for name in names),
        vel=any(name.endswith(VELOCITY_SUFFIX) for name in names),
        torque=any(name.endswith(TORQUE_SUFFIX) for name in names),
        depth=False,
    )
