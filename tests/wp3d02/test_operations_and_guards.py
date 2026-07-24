"""WP-3D-02 — the eight-operation surface, merge delegation, and the copy-on-write guards.

`02b` §8.1 WP-3D-02 makes the deliverable the eight `lerobot-edit-dataset` calls; §8.2
resolves FR-DAT-022 as copy-on-write (original immutable). These tests pin the operation
roster and the engine's refusals: a cross-dataset merge is delegated to WP-3D-06, and no
edit may write over the original.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from backend.dataset.edit import (
    EDIT_OPERATION_NAMES,
    CowInPlaceError,
    DelegatedOperationError,
    DeleteEpisodes,
    MergeDatasets,
    ModifyTasks,
    RecomputeStats,
    ReencodeVideos,
    SplitDataset,
    commit_edit,
)
from tests.wp3d02.support import build_dataset


def test_eight_operations_are_named() -> None:
    """§8.1 The eight lerobot-edit-dataset transformation operations are all provided."""
    assert len(EDIT_OPERATION_NAMES) == 8
    assert set(EDIT_OPERATION_NAMES) == {
        "delete_episodes",
        "split",
        "merge",
        "remove_feature",
        "modify_tasks",
        "convert_image_to_video",
        "recompute_stats",
        "reencode_videos",
    }


def test_renumber_and_in_place_policies_are_declared() -> None:
    """The policies the engine dispatches on match each operation's real behaviour."""
    assert DeleteEpisodes(episode_indices=(0,)).policy.renumbers
    assert SplitDataset(splits={"a": [0]}).policy.renumbers
    assert MergeDatasets(roots=(), repo_ids=()).policy.cross_dataset
    # These mutate the dataset they are handed, so CoW must copy first.
    assert ModifyTasks(new_task="x", episode_tasks=None).policy.in_place
    assert RecomputeStats(skip_image_video=True).policy.in_place
    assert ReencodeVideos().policy.in_place


def test_merge_is_delegated_to_wp_3d_06(tmp_path: Path) -> None:
    """A cross-dataset merge is refused here; its verified remap is WP-3D-06's."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, (3, 4))
    merge = MergeDatasets(roots=(root,), repo_ids=(stamped,))
    with pytest.raises(DelegatedOperationError):
        commit_edit(root, stamped, merge, tmp_path / "m")


def test_output_may_not_overwrite_the_original(tmp_path: Path) -> None:
    """Copy-on-write forbids writing the edit over the original's own root."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, (3, 4))
    with pytest.raises(CowInPlaceError):
        commit_edit(root, stamped, DeleteEpisodes(episode_indices=(0,)), root)


def test_existing_output_is_refused(tmp_path: Path) -> None:
    """An edit refuses to write into a path that already exists."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, (3, 4))
    existing = tmp_path / "already"
    existing.mkdir()
    with pytest.raises(CowInPlaceError):
        commit_edit(root, stamped, DeleteEpisodes(episode_indices=(0,)), existing)
