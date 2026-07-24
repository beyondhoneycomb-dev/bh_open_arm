"""The three recovery means (WP-3C-07 ②): truncate, drop unmatched video, rebuild meta.

`02b` §7 WP-3C-07 ②: "복구 3수단(절단 / 미대응 비디오 제거 / `meta/episodes` 재구성)이
각각 동작". Each means repairs one kind of incomplete-dataset breakage a crash leaves,
and each is a self-contained operation over the recorder's on-disk output:

- `truncate_partial_episode` drops a partial trailing episode's rows from the packed
  data and rewrites a valid parquet — copy-on-write, so a crash *during* recovery never
  produces a second footerless file.
- `drop_unmatched_video` isolates a video segment no `meta/episodes` row references,
  into the recorder band's own quarantine directory (reused, not re-invented).
- `rebuild_episodes_meta` reconstructs `meta/episodes` from the authoritative packed
  data — episode boundaries, lengths and task lists — and restates the `info.json`
  counters, so the metadata agrees with the data after a truncation.

The per-episode statistics `meta/episodes` also carries are NOT recomputed here: that is
WP-3D-03's `compute_stats`, and inventing approximate values would be the kind of
fabricated recovery WP-3B-12 ⑤ forbids. The rebuild restates only the structural
records a reader needs to locate an episode's rows.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from backend.crash_recovery.constants import (
    CHUNK_DIR_PREFIX,
    EPISODE_DATA_CHUNK_COLUMN,
    EPISODE_DATA_FILE_COLUMN,
    EPISODE_FROM_INDEX_COLUMN,
    EPISODE_INDEX_COLUMN,
    EPISODE_LENGTH_COLUMN,
    EPISODE_META_CHUNK_COLUMN,
    EPISODE_META_FILE_COLUMN,
    EPISODE_TASKS_COLUMN,
    EPISODE_TO_INDEX_COLUMN,
    EPISODES_SEGMENT_TEMPLATE,
    FILE_STEM_PREFIX,
    INFO_FPS_KEY,
    INFO_SPLITS_KEY,
    INFO_TOTAL_EPISODES_KEY,
    INFO_TOTAL_FRAMES_KEY,
    INFO_TRAIN_SPLIT_KEY,
    RECOVERY_SCRATCH_SUFFIX,
)
from backend.crash_recovery.layout import (
    data_parquets,
    episodes_meta_parquets,
    read_info,
    referenced_video_files,
    video_files,
    write_info,
)
from backend.recorder.quality.store import DatasetStore

# `LeRobotDataset.create` packs the recorder's small offline datasets into a single
# chunk/file; a rebuild that has no surviving `meta/episodes` to read the packing from
# falls back to this origin, which is where the recorder wrote them.
_DEFAULT_CHUNK_INDEX = 0
_DEFAULT_FILE_INDEX = 0
_TASK_INDEX_COLUMN = "task_index"
_TASKS_PARQUET_RELATIVE = "meta/tasks.parquet"
_TASK_COLUMN = "task"


class RecoveryMeans(StrEnum):
    """The three recovery means WP-3C-07 ② requires to each work."""

    TRUNCATE_PARTIAL_EPISODE = "truncate_partial_episode"
    DROP_UNMATCHED_VIDEO = "drop_unmatched_video"
    REBUILD_EPISODES_META = "rebuild_episodes_meta"


@dataclass(frozen=True)
class TruncateResult:
    """The outcome of truncating a partial episode.

    Attributes:
        episode_index: The episode whose rows were removed.
        rows_removed: How many rows the partial episode held.
        rows_remaining: How many rows survive across the packed data.
        rewritten: The packed parquets rewritten copy-on-write.
    """

    episode_index: int
    rows_removed: int
    rows_remaining: int
    rewritten: tuple[str, ...]


@dataclass(frozen=True)
class DropVideoResult:
    """The outcome of dropping unmatched videos.

    Attributes:
        dropped: The video segments isolated, by their pre-isolation path.
        quarantine_dir: Where they were isolated to.
    """

    dropped: tuple[str, ...]
    quarantine_dir: str


@dataclass(frozen=True)
class RebuildResult:
    """The outcome of rebuilding `meta/episodes`.

    Attributes:
        episode_count: How many episodes the rebuilt metadata describes.
        total_frames: The total row count restated into `info.json`.
        meta_parquet: The single rebuilt `meta/episodes` parquet.
    """

    episode_count: int
    total_frames: int
    meta_parquet: str


def truncate_partial_episode(root: Path, episode_index: int) -> TruncateResult:
    """Remove one episode's rows from the packed data and rewrite valid parquets.

    The rewrite is copy-on-write: each parquet is written to a scratch sibling with a
    complete footer, then atomically renamed over the original, so an interruption
    during recovery leaves either the old file or a fully-footered new one — never a
    second footerless artefact.

    Args:
        root: The dataset root.
        episode_index: The partial episode to drop.

    Returns:
        (TruncateResult) The rows removed, rows remaining, and files rewritten.
    """
    removed = 0
    remaining = 0
    rewritten: list[str] = []
    for parquet in data_parquets(root):
        table = pq.read_table(parquet)
        mask = pc.not_equal(table.column(EPISODE_INDEX_COLUMN), episode_index)
        kept = table.filter(mask)
        removed += table.num_rows - kept.num_rows
        remaining += kept.num_rows
        if kept.num_rows == table.num_rows:
            continue
        _write_cow(parquet, kept)
        rewritten.append(str(parquet))
    return TruncateResult(
        episode_index=episode_index,
        rows_removed=removed,
        rows_remaining=remaining,
        rewritten=tuple(rewritten),
    )


def drop_unmatched_video(root: Path, store: DatasetStore) -> DropVideoResult:
    """Isolate every video segment that no `meta/episodes` row references.

    Reuses the recorder band's quarantine directory (`DatasetStore`) so a crash-isolated
    video lands in the same place as a footerless parquet, rather than a second
    quarantine convention this WP would have to own.

    Args:
        root: The dataset root.
        store: The recorder band's store, whose quarantine directory receives the files.

    Returns:
        (DropVideoResult) The isolated segments and the quarantine directory.
    """
    referenced = referenced_video_files(root)
    unmatched = [video for video in video_files(root) if video not in referenced]
    quarantine = store.ensure_quarantine_dir()
    dropped: list[str] = []
    for video in unmatched:
        destination = quarantine / video.name
        shutil.move(str(video), str(destination))
        dropped.append(str(video))
    return DropVideoResult(dropped=tuple(dropped), quarantine_dir=str(quarantine))


def rebuild_episodes_meta(root: Path) -> RebuildResult:
    """Rebuild `meta/episodes` from the authoritative packed data and restate `info.json`.

    Reads the packed data to recover each episode's boundary, length and task list,
    replaces every `meta/episodes/*` parquet with one rebuilt file, and updates the
    `info.json` episode/frame counters and the single train split so the metadata agrees
    with the data. Per-episode statistics are not recomputed (WP-3D-03 owns that).

    Args:
        root: The dataset root.

    Returns:
        (RebuildResult) The rebuilt episode count, total frames, and the rebuilt file.
    """
    episodes = _scan_episodes(root)
    tasks_by_index = _tasks_by_index(root)

    rows = _episode_rows(episodes, tasks_by_index)
    total_frames = sum(episode.length for episode in episodes)

    for stale in episodes_meta_parquets(root):
        stale.unlink()
    meta_parquet = root / EPISODES_SEGMENT_TEMPLATE.format(
        chunk_index=_DEFAULT_CHUNK_INDEX, file_index=_DEFAULT_FILE_INDEX
    )
    meta_parquet.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), meta_parquet)

    _restate_info(root, len(episodes), total_frames)

    return RebuildResult(
        episode_count=len(episodes),
        total_frames=total_frames,
        meta_parquet=str(meta_parquet),
    )


@dataclass(frozen=True)
class _EpisodeExtent:
    """One episode's boundary as read from the packed data."""

    episode_index: int
    length: int
    task_indices: tuple[int, ...]
    data_chunk_index: int
    data_file_index: int


def _scan_episodes(root: Path) -> list[_EpisodeExtent]:
    """Read every episode's boundary from the packed data, ascending by episode index.

    Args:
        root: The dataset root.

    Returns:
        (list[_EpisodeExtent]) One extent per episode present in the packed data.
    """
    lengths: dict[int, int] = {}
    task_sets: dict[int, list[int]] = {}
    location: dict[int, tuple[int, int]] = {}
    for parquet in data_parquets(root):
        chunk_index, file_index = _packing_of(parquet)
        table = pq.read_table(parquet, columns=[EPISODE_INDEX_COLUMN, _TASK_INDEX_COLUMN])
        episode_column = table.column(EPISODE_INDEX_COLUMN).to_pylist()
        task_column = table.column(_TASK_INDEX_COLUMN).to_pylist()
        for episode_value, task_value in zip(episode_column, task_column, strict=True):
            index = int(episode_value)
            lengths[index] = lengths.get(index, 0) + 1
            location.setdefault(index, (chunk_index, file_index))
            seen = task_sets.setdefault(index, [])
            if int(task_value) not in seen:
                seen.append(int(task_value))
    return [
        _EpisodeExtent(
            episode_index=index,
            length=lengths[index],
            task_indices=tuple(task_sets[index]),
            data_chunk_index=location[index][0],
            data_file_index=location[index][1],
        )
        for index in sorted(lengths)
    ]


def _episode_rows(
    episodes: list[_EpisodeExtent], tasks_by_index: dict[int, str]
) -> list[dict[str, object]]:
    """Assemble the rebuilt `meta/episodes` rows with contiguous dataset ranges.

    Args:
        episodes: The episode extents, ascending by episode index.
        tasks_by_index: The task-index-to-string map.

    Returns:
        (list[dict]) One structural record per episode.
    """
    rows: list[dict[str, object]] = []
    running = 0
    for episode in episodes:
        rows.append(
            {
                EPISODE_INDEX_COLUMN: episode.episode_index,
                EPISODE_TASKS_COLUMN: [
                    tasks_by_index[index]
                    for index in episode.task_indices
                    if index in tasks_by_index
                ],
                EPISODE_LENGTH_COLUMN: episode.length,
                EPISODE_FROM_INDEX_COLUMN: running,
                EPISODE_TO_INDEX_COLUMN: running + episode.length,
                EPISODE_DATA_CHUNK_COLUMN: episode.data_chunk_index,
                EPISODE_DATA_FILE_COLUMN: episode.data_file_index,
                EPISODE_META_CHUNK_COLUMN: _DEFAULT_CHUNK_INDEX,
                EPISODE_META_FILE_COLUMN: _DEFAULT_FILE_INDEX,
            }
        )
        running += episode.length
    return rows


def _tasks_by_index(root: Path) -> dict[int, str]:
    """Read the task-index-to-string map from `meta/tasks.parquet`, if present.

    Args:
        root: The dataset root.

    Returns:
        (dict[int, str]) Task index to its label; empty when the tasks table is absent.
    """
    tasks_parquet = root / _TASKS_PARQUET_RELATIVE
    if not tasks_parquet.is_file():
        return {}
    table = pq.read_table(tasks_parquet)
    indices = table.column(_TASK_INDEX_COLUMN).to_pylist()
    labels = table.column(_TASK_COLUMN).to_pylist()
    return {int(index): str(label) for index, label in zip(indices, labels, strict=True)}


def _restate_info(root: Path, episode_count: int, total_frames: int) -> None:
    """Restate the `info.json` counters and the single train split after a rebuild.

    Args:
        root: The dataset root.
        episode_count: The rebuilt episode count.
        total_frames: The rebuilt total row count.
    """
    info = read_info(root)
    info[INFO_TOTAL_EPISODES_KEY] = episode_count
    info[INFO_TOTAL_FRAMES_KEY] = total_frames
    info[INFO_SPLITS_KEY] = {INFO_TRAIN_SPLIT_KEY: f"0:{episode_count}"}
    info.setdefault(INFO_FPS_KEY, info.get(INFO_FPS_KEY))
    write_info(root, info)


def _write_cow(parquet: Path, table: pa.Table) -> None:
    """Write a table over an existing parquet copy-on-write, footer-complete first.

    Args:
        parquet: The target packed parquet.
        table: The rows to write.
    """
    scratch = parquet.with_suffix(parquet.suffix + RECOVERY_SCRATCH_SUFFIX)
    pq.write_table(table, scratch)
    scratch.replace(parquet)


def _packing_of(parquet: Path) -> tuple[int, int]:
    """Parse the chunk and file index from a packed data parquet path.

    Args:
        parquet: A `data/chunk-{c}/file-{f}.parquet` path.

    Returns:
        (tuple[int, int]) The chunk index and file index, or the origin when the path
            does not carry the packed naming.
    """
    chunk_index = _DEFAULT_CHUNK_INDEX
    file_index = _DEFAULT_FILE_INDEX
    chunk_dir = parquet.parent.name
    if chunk_dir.startswith(CHUNK_DIR_PREFIX):
        chunk_index = int(chunk_dir[len(CHUNK_DIR_PREFIX) :])
    stem = parquet.stem
    if stem.startswith(FILE_STEM_PREFIX):
        file_index = int(stem[len(FILE_STEM_PREFIX) :])
    return chunk_index, file_index
