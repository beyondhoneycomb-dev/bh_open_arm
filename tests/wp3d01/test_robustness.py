"""The reader fires on a corrupt or absent input — it never fakes a green.

A footerless (crash-truncated) parquet, a missing `info.json`, an absent episode
index and an unreadable metadata parquet must each surface as an error, not a
silent empty episode. This is the viewer's half of the load-bearing rule that an
invalid dataset never reads back as valid.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.dataset.viewer import DatasetLayout, DatasetLayoutError, EpisodeViewer
from backend.dataset.viewer.constants import DEFAULT_DATA_PATH_TEMPLATE
from backend.dataset.viewer.signals import read_episode_signals
from tests.wp3d01.materialize import materialize


def test_missing_info_json_raises(tmp_path: Path) -> None:
    (tmp_path / "meta").mkdir()
    with pytest.raises(DatasetLayoutError, match="info.json"):
        DatasetLayout(tmp_path)


def test_absent_episode_raises(tmp_path: Path) -> None:
    spec = materialize(tmp_path, episodes=2, frames=6)
    layout = DatasetLayout(spec.root)
    with pytest.raises(DatasetLayoutError, match="not in the dataset metadata"):
        layout.locate(99)


def test_footerless_data_parquet_fires(tmp_path: Path) -> None:
    spec = materialize(tmp_path, episodes=1, frames=6)
    data_file = spec.root / DEFAULT_DATA_PATH_TEMPLATE.format(chunk_index=0, file_index=0)
    # Truncate the trailing footer + PAR1 magic: the crash signature.
    raw = data_file.read_bytes()
    data_file.write_bytes(raw[: len(raw) - 16])

    layout = DatasetLayout(spec.root)
    with pytest.raises(DatasetLayoutError, match="unreadable"):
        read_episode_signals(layout, 0)


def test_corrupt_episode_metadata_fires(tmp_path: Path) -> None:
    spec = materialize(tmp_path, episodes=1, frames=6)
    meta = spec.root / "meta" / "episodes" / "chunk-000" / "file-000.parquet"
    meta.write_bytes(b"not a parquet file")
    with pytest.raises(DatasetLayoutError, match="unreadable"):
        DatasetLayout(spec.root)


def test_missing_video_file_leaves_no_phantom_segment(tmp_path: Path) -> None:
    # A dataset whose mp4 is absent must not claim a video segment for it; the
    # viewer resolves such a stream through the image path instead of inventing one.
    spec = materialize(tmp_path, episodes=1, frames=6)
    for rgb_key in spec.rgb_keys:
        video = spec.root / "videos" / rgb_key / "chunk-000" / "file-000.mp4"
        video.unlink()
    layout = DatasetLayout(spec.root)
    location = layout.locate(0)
    assert location.video_segments == {}


def test_open_and_close_releases_containers(tmp_path: Path) -> None:
    spec = materialize(tmp_path, episodes=1, frames=6)
    viewer = EpisodeViewer.open(spec.root, 0)
    viewer.frame_by_index(0)
    viewer.close()
    # Closing twice is safe (idempotent release).
    viewer.close()
