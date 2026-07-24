"""Read-only access to the recorder's on-disk v3.0 dataset (WP-3C-07 data edge).

WP-3C-07 consumes the WP-3B-11 recorder's *output* — it reads `meta/info.json`, the
packed `data/chunk-*/file-*.parquet`, the `meta/episodes/*` metadata and the
`videos/*` tree as files, and joins them by episode index. It does not import the
recorder's writing API; this module is the whole of that file-level read surface, so
the data join is in one place rather than re-derived in every recovery means (`02b`
§7 WP-3C-07 참조근거, `06` §5.6).

Reading a packed parquet needs pyarrow, imported at module load: this module is part
of the robot/data backend, never the light registry lane, so the dependency is always
present where it runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from backend.crash_recovery.constants import (
    DATA_DIR,
    EPISODE_INDEX_COLUMN,
    EPISODES_META_DIR,
    INFO_RELATIVE_PATH,
    JOURNAL_ENCODING,
    MP4_FILE_GLOB,
    PARQUET_FILE_GLOB,
    VIDEO_CHUNK_COLUMN_SUFFIX,
    VIDEO_FILE_COLUMN_SUFFIX,
    VIDEO_SEGMENT_TEMPLATE,
    VIDEOS_DIR,
)


def info_path(root: Path) -> Path:
    """The dataset's `meta/info.json` path."""
    return root / INFO_RELATIVE_PATH


def read_info(root: Path) -> dict[str, object]:
    """Read and parse `meta/info.json`.

    Args:
        root: The dataset root (the directory holding `meta/`, `data/`, `videos/`).

    Returns:
        (dict) The parsed metadata.

    Raises:
        FileNotFoundError: When `info.json` is absent.
    """
    body = info_path(root).read_text(encoding=JOURNAL_ENCODING)
    return json.loads(body)


def write_info(root: Path, info: dict[str, object]) -> None:
    """Write `meta/info.json` back after a rebuild restated its counters.

    Args:
        root: The dataset root.
        info: The updated metadata.
    """
    text = json.dumps(info, ensure_ascii=False, indent=1)
    info_path(root).write_text(text, encoding=JOURNAL_ENCODING)


def data_parquets(root: Path) -> list[Path]:
    """Every packed data parquet under `data/`, in chunk/file order.

    Args:
        root: The dataset root.

    Returns:
        (list[Path]) The packed data parquets, empty when the tree is absent.
    """
    data_dir = root / DATA_DIR
    if not data_dir.is_dir():
        return []
    return sorted(data_dir.rglob(PARQUET_FILE_GLOB))


def episodes_meta_parquets(root: Path) -> list[Path]:
    """Every `meta/episodes/*` metadata parquet, in chunk/file order.

    Args:
        root: The dataset root.

    Returns:
        (list[Path]) The episode-metadata parquets, empty when the tree is absent.
    """
    meta_dir = root / EPISODES_META_DIR
    if not meta_dir.is_dir():
        return []
    return sorted(meta_dir.rglob(PARQUET_FILE_GLOB))


def video_files(root: Path) -> list[Path]:
    """Every video segment under `videos/`, in path order.

    Args:
        root: The dataset root.

    Returns:
        (list[Path]) The video files, empty when the tree is absent.
    """
    videos_dir = root / VIDEOS_DIR
    if not videos_dir.is_dir():
        return []
    return sorted(videos_dir.rglob(MP4_FILE_GLOB))


def episode_row_counts(root: Path) -> dict[int, int]:
    """Count the packed rows of every episode present in the data parquets.

    The truncate and rebuild means both key off this: it is the ground truth of what
    the data *actually* holds, read straight from the `episode_index` column rather
    than from the possibly-stale `meta/episodes` records.

    Args:
        root: The dataset root.

    Returns:
        (dict[int, int]) Episode index to its packed row count, ascending by index.
    """
    counts: dict[int, int] = {}
    for parquet in data_parquets(root):
        column = pq.read_table(parquet, columns=[EPISODE_INDEX_COLUMN]).column(EPISODE_INDEX_COLUMN)
        for value in column.to_pylist():
            index = int(value)
            counts[index] = counts.get(index, 0) + 1
    return dict(sorted(counts.items()))


def referenced_video_files(root: Path) -> set[Path]:
    """Resolve the video files that `meta/episodes/*` actually references.

    A v3.0 dataset with cameras stores, per episode, the chunk/file index of each
    video key's segment. A video file on disk that no episode row points at is
    unmatched — the artefact `drop_unmatched_video` removes. A state/action-only
    dataset has no video columns, so this is the empty set and every video on disk is
    unmatched by construction.

    Args:
        root: The dataset root.

    Returns:
        (set[Path]) Absolute paths of every video segment an episode references.
    """
    referenced: set[Path] = set()
    for parquet in episodes_meta_parquets(root):
        table = pq.read_table(parquet)
        for column_name in table.column_names:
            if not _is_video_chunk_column(column_name):
                continue
            video_key = _video_key_of(column_name)
            file_column = f"{VIDEOS_DIR}/{video_key}{VIDEO_FILE_COLUMN_SUFFIX}"
            if file_column not in table.column_names:
                continue
            chunks = table.column(column_name).to_pylist()
            files = table.column(file_column).to_pylist()
            for chunk_index, file_index in zip(chunks, files, strict=True):
                if chunk_index is None or file_index is None:
                    continue
                segment = VIDEO_SEGMENT_TEMPLATE.format(
                    video_key=video_key,
                    chunk_index=int(chunk_index),
                    file_index=int(file_index),
                )
                referenced.add(root / segment)
    return referenced


def _is_video_chunk_column(column_name: str) -> bool:
    """Whether a `meta/episodes` column names a video key's chunk index."""
    return column_name.startswith(f"{VIDEOS_DIR}/") and column_name.endswith(
        VIDEO_CHUNK_COLUMN_SUFFIX
    )


def _video_key_of(column_name: str) -> str:
    """Extract the video key from a `videos/<key>/chunk_index` column name."""
    return column_name[len(f"{VIDEOS_DIR}/") : -len(VIDEO_CHUNK_COLUMN_SUFFIX)]
