"""The queryable reverse-lineage store (WP-3D-04), backed by SQLite.

LeRobot restores lineage *forward* only: from a `train_config.json` it can rebuild
which dataset and episodes a run consumed. The reverse — "which checkpoints used
this episode" — is ours (`02b` §8.2 WP-3D-04), and this module is it: a two-table
SQLite store whose `run_episode` table is exactly the inverted index LeRobot never
keeps, so the reverse query is a single join.

Four capabilities the acceptance turns on live here:
- the reverse query (① `checkpoints_for_episode`);
- the read-back that reproduces a full record, channel selection included (③);
- the pre-delete reference query and warning (④ `guard_delete`); and
- the integrity scan (`verify_mappings`) that fires when any run has no episode
  mapping — a missing mapping is `FAIL_BLOCKING`, so it must be detectable after the
  fact, not only refused at write time.

Every write goes through `LineageRecord.validate()` first, so a hole cannot enter
through the front door; `verify_mappings` is the guard against one entering through
external tampering with the file.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from backend.dataset.lineage.channels import ChannelSelection
from backend.dataset.lineage.constants import (
    FOREIGN_KEYS_PRAGMA,
    RUN_EPISODE_TABLE,
    RUN_TABLE,
    SCHEMA_VERSION,
)
from backend.dataset.lineage.record import LineageError, LineageRecord

_SCHEMA_META_TABLE = "schema_meta"
_SCHEMA_VERSION_KEY = "schema_version"


@dataclass(frozen=True)
class CheckpointRef:
    """A checkpoint the reverse query and the delete guard return.

    Attributes:
        output_dir: The training run's output directory.
        step: The checkpoint step; `output_dir` + step is the checkpoint identity.
        repo_id: The stamped `repo_id` of the dataset the checkpoint trained on.
        dataset_content_hash: The content hash of that dataset version.
        revision: The dataset revision.
        stats_hash: The normalisation-statistics hash the checkpoint fit.
    """

    output_dir: str
    step: int
    repo_id: str
    dataset_content_hash: str
    revision: str
    stats_hash: str


@dataclass(frozen=True)
class DeleteGuard:
    """The result of asking whether a dataset is safe to delete (WP-3D-04 ④).

    Attributes:
        dataset_content_hash: The dataset version the caller intends to delete.
        referencing: The checkpoints that trained on it, empty when none.
    """

    dataset_content_hash: str
    referencing: tuple[CheckpointRef, ...]

    @property
    def safe(self) -> bool:
        """Whether no checkpoint references the dataset, so deletion loses no lineage."""
        return not self.referencing

    def warning(self) -> str:
        """A human-readable warning naming the referencing checkpoints, or empty.

        Returns:
            (str) One line per referencing checkpoint, or "" when deletion is safe.
        """
        if self.safe:
            return ""
        lines = [
            f"dataset {self.dataset_content_hash} is referenced by {len(self.referencing)} "
            "checkpoint(s); deleting it will orphan their lineage:"
        ]
        lines.extend(
            f"  - {ref.output_dir}@{ref.step} (repo_id={ref.repo_id})" for ref in self.referencing
        )
        return "\n".join(lines)


class LineageStore:
    """A SQLite-backed store for reverse dataset/episode lineage.

    Owns one connection for its lifetime; open it as a context manager, or call
    `close()`. Foreign keys are enabled per connection so the `run_episode` rows
    cascade-delete with their run. A store opened on an existing file verifies the
    schema generation and refuses a mismatch rather than misreading old bytes.
    """

    def __init__(self, path: str | Path) -> None:
        """Open (creating if absent) the store at `path`.

        Args:
            path: A filesystem path, or `":memory:"` for a throwaway store.

        Raises:
            LineageError: When an existing file's schema generation is not this one.
        """
        self.mPath = str(path)
        self.mConnection = sqlite3.connect(self.mPath)
        self.mConnection.row_factory = sqlite3.Row
        self.mConnection.execute(FOREIGN_KEYS_PRAGMA)
        self._ensure_schema()

    def __enter__(self) -> LineageStore:
        """Enter the runtime context, returning this store."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection on context exit."""
        self.close()

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        self.mConnection.close()

    def _ensure_schema(self) -> None:
        """Create the tables on a fresh store, or verify the generation on an old one.

        Raises:
            LineageError: When an existing store's stamped generation differs from
                `SCHEMA_VERSION`.
        """
        existing = self.mConnection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (_SCHEMA_META_TABLE,),
        ).fetchone()
        if existing is None:
            self._create_schema()
            return
        stored = self.mConnection.execute(
            f"SELECT value FROM {_SCHEMA_META_TABLE} WHERE key=?",
            (_SCHEMA_VERSION_KEY,),
        ).fetchone()
        if stored is None or int(stored["value"]) != SCHEMA_VERSION:
            found = None if stored is None else stored["value"]
            raise LineageError(
                f"lineage store at {self.mPath} is schema version {found}, expected "
                f"{SCHEMA_VERSION}; refusing to misread an incompatible generation"
            )

    def _create_schema(self) -> None:
        """Create the two lineage tables, their indexes, and stamp the generation."""
        with self.mConnection:
            self.mConnection.executescript(
                f"""
                CREATE TABLE {_SCHEMA_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE {RUN_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_id TEXT NOT NULL,
                    dataset_content_hash TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    stats_hash TEXT NOT NULL,
                    use_velocity_and_torque INTEGER NOT NULL,
                    state_dim INTEGER NOT NULL,
                    encoder_settings TEXT NOT NULL,
                    channel_selection TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    UNIQUE (output_dir, step)
                );
                CREATE TABLE {RUN_EPISODE_TABLE} (
                    run_id INTEGER NOT NULL REFERENCES {RUN_TABLE}(id) ON DELETE CASCADE,
                    episode_index INTEGER NOT NULL,
                    PRIMARY KEY (run_id, episode_index)
                );
                CREATE INDEX idx_run_episode_episode ON {RUN_EPISODE_TABLE}(episode_index);
                CREATE INDEX idx_run_dataset ON {RUN_TABLE}(dataset_content_hash);
                """
            )
            self.mConnection.execute(
                f"INSERT INTO {_SCHEMA_META_TABLE} (key, value) VALUES (?, ?)",
                (_SCHEMA_VERSION_KEY, str(SCHEMA_VERSION)),
            )

    def record(self, entry: LineageRecord) -> int:
        """Validate and store one training run's lineage, returning its row id.

        The run row and every `run_episode` row are inserted in one transaction, so
        a run can never land without its episode mapping. A duplicate checkpoint
        identity (`output_dir` + step) is refused: a checkpoint's lineage is written
        once and is immutable.

        Args:
            entry: The record to store; validated before any write.

        Returns:
            (int) The new run's row id.

        Raises:
            LineageError: When the record is invalid (including an empty episode
                mapping) or its checkpoint identity is already stored.
        """
        entry.validate()
        try:
            with self.mConnection:
                cursor = self.mConnection.execute(
                    f"""
                    INSERT INTO {RUN_TABLE} (
                        repo_id, dataset_content_hash, revision, stats_hash,
                        use_velocity_and_torque, state_dim, encoder_settings,
                        channel_selection, output_dir, step
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.repo_id,
                        entry.dataset_content_hash,
                        entry.revision,
                        entry.stats_hash,
                        int(entry.use_velocity_and_torque),
                        entry.state_dim,
                        entry.encoder_settings_json(),
                        entry.channels.to_json(),
                        entry.output_dir,
                        entry.step,
                    ),
                )
                run_id = int(cursor.lastrowid or 0)
                self.mConnection.executemany(
                    f"INSERT INTO {RUN_EPISODE_TABLE} (run_id, episode_index) VALUES (?, ?)",
                    [(run_id, index) for index in entry.episodes],
                )
        except sqlite3.IntegrityError as clash:
            raise LineageError(
                f"checkpoint {entry.output_dir}@{entry.step} is already recorded; "
                "a checkpoint's lineage is immutable"
            ) from clash
        return run_id

    def checkpoints_for_episode(
        self, dataset_content_hash: str, episode_index: int
    ) -> tuple[CheckpointRef, ...]:
        """Return every checkpoint that trained on one episode of one dataset.

        This is the reverse query (① and the WP-3D-04 invariant): the answer LeRobot
        cannot give, because it keeps no episode-to-checkpoint index.

        Args:
            dataset_content_hash: The dataset version's content hash.
            episode_index: The episode within that dataset.

        Returns:
            (tuple[CheckpointRef, ...]) Referencing checkpoints, ordered by
                `output_dir` then step; empty when none.
        """
        rows = self.mConnection.execute(
            f"""
            SELECT r.output_dir, r.step, r.repo_id, r.dataset_content_hash,
                   r.revision, r.stats_hash
            FROM {RUN_TABLE} r
            JOIN {RUN_EPISODE_TABLE} e ON e.run_id = r.id
            WHERE r.dataset_content_hash = ? AND e.episode_index = ?
            ORDER BY r.output_dir, r.step
            """,
            (dataset_content_hash, episode_index),
        ).fetchall()
        return tuple(_checkpoint_ref(row) for row in rows)

    def references_for_dataset(self, dataset_content_hash: str) -> tuple[CheckpointRef, ...]:
        """Return every checkpoint that trained on any episode of one dataset.

        Args:
            dataset_content_hash: The dataset version's content hash.

        Returns:
            (tuple[CheckpointRef, ...]) Referencing checkpoints, ordered by
                `output_dir` then step; empty when none.
        """
        rows = self.mConnection.execute(
            f"""
            SELECT output_dir, step, repo_id, dataset_content_hash, revision, stats_hash
            FROM {RUN_TABLE}
            WHERE dataset_content_hash = ?
            ORDER BY output_dir, step
            """,
            (dataset_content_hash,),
        ).fetchall()
        return tuple(_checkpoint_ref(row) for row in rows)

    def guard_delete(self, dataset_content_hash: str) -> DeleteGuard:
        """Ask whether a dataset is safe to delete, listing referencing checkpoints.

        The store never deletes the dataset itself — that is a filesystem action; it
        reports what would be orphaned so the caller can warn and refuse (④).

        Args:
            dataset_content_hash: The dataset version the caller intends to delete.

        Returns:
            (DeleteGuard) The referencing checkpoints and a `safe` verdict.
        """
        return DeleteGuard(
            dataset_content_hash=dataset_content_hash,
            referencing=self.references_for_dataset(dataset_content_hash),
        )

    def verify_mappings(self) -> tuple[str, ...]:
        """Return one message per run that has no episode mapping (a lineage hole).

        `record()` refuses an empty mapping at write time; this is the after-the-fact
        guard against a hole introduced by external tampering with the file. A
        non-empty result is `FAIL_BLOCKING` for the traceability CI.

        Returns:
            (tuple[str, ...]) Descriptions of runs with zero `run_episode` rows,
                ordered by checkpoint identity; empty when every run is mapped.
        """
        rows = self.mConnection.execute(
            f"""
            SELECT r.output_dir, r.step, r.repo_id
            FROM {RUN_TABLE} r
            LEFT JOIN {RUN_EPISODE_TABLE} e ON e.run_id = r.id
            WHERE e.run_id IS NULL
            ORDER BY r.output_dir, r.step
            """
        ).fetchall()
        return tuple(
            f"checkpoint {row['output_dir']}@{int(row['step'])} (repo_id={row['repo_id']}) "
            "has no episode mapping (FAIL_BLOCKING)"
            for row in rows
        )

    def get(self, output_dir: str, step: int) -> LineageRecord | None:
        """Read one checkpoint's full record back, or None when it is not stored.

        The reconstruction includes the episode mapping and the channel selection,
        which is what proves the ③ channel state is reproducible from the store.

        Args:
            output_dir: The run's output directory.
            step: The checkpoint step.

        Returns:
            (LineageRecord | None) The reconstructed record, or None when absent.
        """
        row = self.mConnection.execute(
            f"""
            SELECT id, repo_id, dataset_content_hash, revision, stats_hash,
                   use_velocity_and_torque, state_dim, encoder_settings,
                   channel_selection, output_dir, step
            FROM {RUN_TABLE}
            WHERE output_dir = ? AND step = ?
            """,
            (output_dir, step),
        ).fetchone()
        if row is None:
            return None
        episodes = self.mConnection.execute(
            f"""
            SELECT episode_index FROM {RUN_EPISODE_TABLE}
            WHERE run_id = ? ORDER BY episode_index
            """,
            (int(row["id"]),),
        ).fetchall()
        encoder_settings: Mapping[str, Any] = json.loads(row["encoder_settings"])
        return LineageRecord(
            repo_id=str(row["repo_id"]),
            dataset_content_hash=str(row["dataset_content_hash"]),
            revision=str(row["revision"]),
            episodes=tuple(int(episode["episode_index"]) for episode in episodes),
            stats_hash=str(row["stats_hash"]),
            use_velocity_and_torque=bool(row["use_velocity_and_torque"]),
            state_dim=int(row["state_dim"]),
            encoder_settings=encoder_settings,
            channels=ChannelSelection.from_json(str(row["channel_selection"])),
            output_dir=str(row["output_dir"]),
            step=int(row["step"]),
        )


def _checkpoint_ref(row: sqlite3.Row) -> CheckpointRef:
    """Build a `CheckpointRef` from a query row carrying its six columns."""
    return CheckpointRef(
        output_dir=str(row["output_dir"]),
        step=int(row["step"]),
        repo_id=str(row["repo_id"]),
        dataset_content_hash=str(row["dataset_content_hash"]),
        revision=str(row["revision"]),
        stats_hash=str(row["stats_hash"]),
    )
