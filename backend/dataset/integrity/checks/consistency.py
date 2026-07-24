"""Check 2 — `info.json` agrees with the chunk/file layout (`02b` §8.2 WP-3D-05).

`meta/info.json` declares the feature set and the `data_path`/`video_path`
templates; the episode metadata declares each episode's chunk and file indices.
Together they claim a set of files and columns. This check confirms the claim
holds on disk: every episode's data parquet and RGB video resolve to a file that
exists, and every non-image feature `info.json` declares is a real column of the
data parquet. A feature named in `info.json` but absent from the parquet is the
classic drift — the metadata and the bytes disagree about what the dataset holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from backend.dataset.integrity.constants import CHECK_INFO_CHUNK_CONSISTENCY
from backend.dataset.integrity.dataset import DatasetInventory, InventoryError, _scalar
from backend.dataset.integrity.report import CheckResult, failed, passed
from backend.dataset.viewer.constants import (
    video_chunk_index_column,
    video_file_index_column,
)
from backend.dataset.viewer.layout import DatasetLayout


def check_info_chunk_consistency(inventory: DatasetInventory) -> CheckResult:
    """Verify `info.json` templates/features resolve to the files and columns on disk.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) PASS when files resolve and every stored feature is a
            parquet column; FAIL naming the first missing file or column.
    """
    try:
        layout = inventory.require_layout()
    except InventoryError as bad:
        return failed(CHECK_INFO_CHUNK_CONSISTENCY, f"info.json/layout unreadable: {bad}")

    image_keys = inventory.image_feature_keys()
    rgb_keys = tuple(stream.image_key for stream in layout.camera_streams() if not stream.is_depth)

    for episode_index in layout.episode_indices() or (0,):
        location = layout.locate(episode_index)
        if not location.data_file.is_file():
            return failed(
                CHECK_INFO_CHUNK_CONSISTENCY,
                f"episode {episode_index} data file {location.data_file} does not exist",
            )
        row = layout.episodes.get(episode_index, {})
        for key in rgb_keys:
            video_path = _resolve_video(layout, key, row)
            if not video_path.is_file():
                return failed(
                    CHECK_INFO_CHUNK_CONSISTENCY,
                    f"episode {episode_index} video {video_path} for {key} does not exist",
                )

    stored = frozenset(key for key in layout.features if key not in image_keys)
    for data_file in inventory.data_files():
        try:
            columns = frozenset(pq.read_schema(data_file).names)
        except Exception as bad:  # noqa: BLE001 — an unreadable schema is a consistency failure
            return failed(CHECK_INFO_CHUNK_CONSISTENCY, f"{data_file}: schema unreadable ({bad})")
        missing = stored - columns
        if missing:
            return failed(
                CHECK_INFO_CHUNK_CONSISTENCY,
                f"{data_file}: info.json features {sorted(missing)} are not parquet columns",
            )

    return passed(
        CHECK_INFO_CHUNK_CONSISTENCY,
        f"{len(stored)} stored feature(s) and all chunk/file paths resolve",
    )


def _resolve_video(layout: DatasetLayout, image_key: str, row: dict[str, Any]) -> Path:
    """Resolve an RGB stream's mp4 path from the `video_path` template and row indices."""
    chunk = _scalar(row.get(video_chunk_index_column(image_key), 0)) or 0
    file_index = _scalar(row.get(video_file_index_column(image_key), 0)) or 0
    return layout.root / layout.video_path_template.format(
        video_key=image_key, chunk_index=int(chunk), file_index=int(file_index)
    )
