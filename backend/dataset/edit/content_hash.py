"""Per-episode content identity, the join a sidecar remap is verified against (WP-3D-02).

`02b` §8.2 WP-3D-02 ① requires the sidecar cross-check to be keyed on the episode's
*content*, not its index: "에피소드 내용 해시 → 라벨 역조회". A renumber rewrites
`episode_index`/`index`; a content hash computed over the recorded frames survives it,
so the same episode hashes identically before and after it is moved, and the remap can
prove — for every episode, no sampling — that a label still sits on the frames it was
written for.

The hash is read straight from the parquet shards (`FR-DAT-009` direct read), never
through a decode of the video streams, so it is cheap enough to run over every episode
of both the original and the edited dataset on each edit.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd
from lerobot.datasets.utils import DEFAULT_DATA_PATH

from backend.dataset.edit.constants import (
    EPISODE_DATA_CHUNK_KEY,
    EPISODE_DATA_FILE_KEY,
    EPISODE_INDEX_COLUMN,
    FRAME_INDEX_COLUMN,
    IDENTITY_COLUMNS,
    IDENTITY_CONTENT_COLUMNS,
)


class ContentHashError(ValueError):
    """An episode carries no hashable recorded content, so it cannot be identified.

    Raised when none of the identity content columns (`action`, `observation.state`)
    is present: with no recorded content there is nothing to anchor a label to, and a
    remap that guessed would be the FAIL_BLOCKING "label on the wrong episode" defect.
    """


def _episode_shard_path(dataset: Any, episode_index: int) -> Any:
    """Return the parquet path holding one episode's frames.

    Args:
        dataset: A loaded `LeRobotDataset`.
        episode_index: The episode whose data shard is wanted.

    Returns:
        The absolute path to the episode's data parquet.
    """
    meta = dataset.meta.episodes[episode_index]
    return dataset.root / DEFAULT_DATA_PATH.format(
        chunk_index=meta[EPISODE_DATA_CHUNK_KEY],
        file_index=meta[EPISODE_DATA_FILE_KEY],
    )


def _hash_frame_rows(rows: pd.DataFrame) -> str:
    """Hash one episode's frames over the index-independent identity columns.

    The rows are sorted by frame index first, so the hash is invariant to the row
    order the parquet happens to store, and each present identity column is folded in
    under its own name so a value cannot silently migrate between columns.

    Args:
        rows: The frames of a single episode.

    Returns:
        (str) A hex digest identifying the episode's content.

    Raises:
        ContentHashError: When no recorded-content column is present.
    """
    if not any(column in rows.columns for column in IDENTITY_CONTENT_COLUMNS):
        raise ContentHashError(
            "episode has none of "
            f"{IDENTITY_CONTENT_COLUMNS}; there is no recorded content to identify it by"
        )
    ordered = rows.sort_values(FRAME_INDEX_COLUMN)
    digest = hashlib.sha256()
    for column in IDENTITY_COLUMNS:
        if column not in ordered.columns:
            continue
        series = ordered[column].to_numpy()
        # A vector-valued column (action, observation.state) arrives as an object
        # array of per-row arrays; stack it into one contiguous float block so the
        # bytes are stable across pandas/pyarrow round-trips.
        if series.dtype == object:
            values = np.stack([np.asarray(item, dtype=np.float64) for item in series])
        else:
            values = np.ascontiguousarray(series, dtype=np.float64)
        digest.update(column.encode("utf-8"))
        digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def episode_content_hashes(dataset: Any) -> dict[int, str]:
    """Hash every episode of a dataset by its recorded content.

    Reads each data shard once and groups its episodes, so a chunked dataset is not
    re-read per episode. The result is the reverse-lookup table `02b` §8.2 WP-3D-02 ①
    joins on: content hash to episode index.

    Args:
        dataset: A loaded `LeRobotDataset`.

    Returns:
        (dict[int, str]) Episode index to content hash, for every episode.

    Raises:
        ContentHashError: When any episode carries no hashable content.
    """
    shards: dict[Any, pd.DataFrame] = {}
    hashes: dict[int, str] = {}
    for episode_index in range(dataset.meta.total_episodes):
        path = _episode_shard_path(dataset, episode_index)
        if path not in shards:
            shards[path] = pd.read_parquet(path)
        frame = shards[path]
        rows = frame[frame[EPISODE_INDEX_COLUMN] == episode_index]
        hashes[episode_index] = _hash_frame_rows(rows)
    return hashes
