"""WP-3C-07 ②: the three recovery means each work.

`02b` §7 WP-3C-07 ②: "복구 3수단(절단 / 미대응 비디오 제거 / `meta/episodes` 재구성)이
각각 동작". Each means is exercised on the incomplete-dataset artefact its matching fault
leaves, and each is checked to actually repair the dataset — a truncation that removes
the partial episode and leaves a readable parquet, a drop that isolates the unmatched
video, and a rebuild that restores `meta/episodes` and the `info.json` counters from the
authoritative packed data.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from backend.crash_recovery.constants import (
    EPISODE_FROM_INDEX_COLUMN,
    EPISODE_INDEX_COLUMN,
    EPISODE_LENGTH_COLUMN,
    EPISODE_TO_INDEX_COLUMN,
    INFO_TOTAL_EPISODES_KEY,
    INFO_TOTAL_FRAMES_KEY,
)
from backend.crash_recovery.faults import inject_disk_full, inject_network_cut
from backend.crash_recovery.layout import (
    episode_row_counts,
    episodes_meta_parquets,
    read_info,
    referenced_video_files,
    video_files,
)
from backend.crash_recovery.recovery import (
    drop_unmatched_video,
    rebuild_episodes_meta,
    truncate_partial_episode,
)
from backend.recorder.quality.store import DatasetStore
from tests.wp3c07.support import EPISODE_STEPS, build_baseline_dataset

_BASELINE_EPISODES = 2
_PARTIAL_ROWS = 2
_VIDEO_KEY = "observation.images.cam_high"


def test_truncate_removes_the_partial_episode_and_leaves_a_readable_parquet(
    tmp_path: Path,
) -> None:
    """Truncate drops the partial episode's rows and rewrites a valid, readable parquet."""
    root = tmp_path / "ds"
    build_baseline_dataset(root, _BASELINE_EPISODES)
    fault = inject_disk_full(root, partial_rows=_PARTIAL_ROWS)
    partial_index = fault.partial_episode_index
    assert partial_index is not None
    assert episode_row_counts(root)[partial_index] == _PARTIAL_ROWS

    result = truncate_partial_episode(root, partial_index)

    assert result.rows_removed == _PARTIAL_ROWS
    assert partial_index not in episode_row_counts(root)
    assert result.rows_remaining == _BASELINE_EPISODES * EPISODE_STEPS
    # Every rewritten parquet is complete: a readable footer, no second crash artefact.
    for rewritten in result.rewritten:
        table = pq.read_table(rewritten)
        assert partial_index not in table.column(EPISODE_INDEX_COLUMN).to_pylist()


def test_drop_unmatched_video_isolates_the_orphaned_segment(tmp_path: Path) -> None:
    """Drop moves a video no episode references into quarantine, leaving the tree clean."""
    root = tmp_path / "ds"
    build_baseline_dataset(root, _BASELINE_EPISODES)
    fault = inject_network_cut(root, video_key=_VIDEO_KEY)
    assert fault.unmatched_video in video_files(root)
    # A state/action dataset references no video, so the injected segment is unmatched.
    assert referenced_video_files(root) == set()

    result = drop_unmatched_video(root, DatasetStore(root=root))

    assert len(result.dropped) == 1
    assert fault.unmatched_video is not None
    assert not fault.unmatched_video.exists()
    quarantined = Path(result.quarantine_dir) / fault.unmatched_video.name
    assert quarantined.is_file()


def test_drop_unmatched_video_keeps_referenced_segments(tmp_path: Path) -> None:
    """Drop leaves alone a dataset whose videos are all referenced — no false isolation."""
    root = tmp_path / "ds"
    build_baseline_dataset(root, _BASELINE_EPISODES)

    result = drop_unmatched_video(root, DatasetStore(root=root))

    assert result.dropped == ()


def test_rebuild_meta_reconstructs_episodes_from_the_packed_data(tmp_path: Path) -> None:
    """Rebuild restores a deleted `meta/episodes` from the packed data, contiguous ranges."""
    root = tmp_path / "ds"
    build_baseline_dataset(root, _BASELINE_EPISODES)
    for meta in episodes_meta_parquets(root):
        meta.unlink()
    assert episodes_meta_parquets(root) == []

    result = rebuild_episodes_meta(root)

    assert result.episode_count == _BASELINE_EPISODES
    assert result.total_frames == _BASELINE_EPISODES * EPISODE_STEPS
    table = pq.read_table(result.meta_parquet)
    assert table.column(EPISODE_INDEX_COLUMN).to_pylist() == list(range(_BASELINE_EPISODES))
    assert table.column(EPISODE_LENGTH_COLUMN).to_pylist() == [EPISODE_STEPS] * _BASELINE_EPISODES
    assert table.column(EPISODE_FROM_INDEX_COLUMN).to_pylist() == [0, EPISODE_STEPS]
    assert table.column(EPISODE_TO_INDEX_COLUMN).to_pylist() == [EPISODE_STEPS, 2 * EPISODE_STEPS]


def test_rebuild_meta_restates_info_counters(tmp_path: Path) -> None:
    """Rebuild updates `info.json` totals and the train split to match the packed data."""
    root = tmp_path / "ds"
    build_baseline_dataset(root, _BASELINE_EPISODES)

    rebuild_episodes_meta(root)

    info = read_info(root)
    assert info[INFO_TOTAL_EPISODES_KEY] == _BASELINE_EPISODES
    assert info[INFO_TOTAL_FRAMES_KEY] == _BASELINE_EPISODES * EPISODE_STEPS


def test_truncate_then_rebuild_agree_after_a_disk_full(tmp_path: Path) -> None:
    """The disk-full pair — truncate then rebuild — leaves data and metadata consistent."""
    root = tmp_path / "ds"
    build_baseline_dataset(root, _BASELINE_EPISODES)
    fault = inject_disk_full(root, partial_rows=_PARTIAL_ROWS)
    assert fault.partial_episode_index is not None

    truncate_partial_episode(root, fault.partial_episode_index)
    result = rebuild_episodes_meta(root)

    assert result.episode_count == _BASELINE_EPISODES
    assert result.total_frames == sum(episode_row_counts(root).values())
