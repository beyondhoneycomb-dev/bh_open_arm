"""WP-3D-02 core — a delete renumbers, and the sidecars follow the content, not the index.

`02b` §8.2 WP-3D-02 ①④⑤⑥: after a renumber the sidecar references cross-check 100% (no
sampling), the commit preview states the five figures, the output loads once as a dataset,
and copy-on-write keeps the original beside the new version. The FAIL_BLOCKING this proves
the absence of: "라벨이 다른 에피소드에 들러붙는다" — a label sticking to a different episode.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.edit import DeleteEpisodes, commit_edit, disk_precheck
from backend.recorder.quality.label import Verdict
from backend.recorder.quality.store import DatasetStore
from tests.wp3d02.support import build_dataset, write_labels

# Four episodes of distinct length and content; episode 1 (a FAIL) is deleted, so the
# survivors 0, 2, 3 renumber to 0, 1, 2 and their labels must renumber with them.
_FRAME_COUNTS = (3, 4, 5, 6)
_VERDICTS = (Verdict.SUCCESS, Verdict.FAIL, Verdict.SUCCESS, Verdict.FAIL)


def _committed(tmp_path: Path):
    """Build a labelled four-episode dataset and delete episode 1 under CoW."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS)
    write_labels(root, _VERDICTS)
    output = tmp_path / "ds_edited"
    result = commit_edit(root, stamped, DeleteEpisodes(episode_indices=(1,)), output)
    return root, output, result


def test_labels_follow_content_across_the_renumber(tmp_path: Path) -> None:
    """① The remapped sidecar at each new index carries the deleted-aware original label."""
    _root, output, result = _committed(tmp_path)
    store = DatasetStore(output)

    # Survivors old 0,2,3 -> new 0,1,2; verdicts SUCCESS, SUCCESS, FAIL follow the content.
    expected = {0: Verdict.SUCCESS.value, 1: Verdict.SUCCESS.value, 2: Verdict.FAIL.value}
    for new_index, verdict in expected.items():
        body = json.loads(store.sidecar_path(new_index).read_text(encoding="utf-8"))
        assert body["episode_index"] == new_index
        assert body["label"]["episode_index"] == new_index
        assert body["label"]["manual"]["verdict"] == verdict

    assert result.outputs["output"].episode_mapping == {0: 0, 1: 2, 2: 3}
    assert result.outputs["output"].remapped_sidecars == [0, 1, 2]


def test_cross_check_is_total_no_sampling(tmp_path: Path) -> None:
    """① Every produced episode has a remapped sidecar — the join is over all, not a sample."""
    _root, output, result = _committed(tmp_path)
    produced = LeRobotDataset(result.outputs["output"].repo_id, root=output)
    written = set(DatasetStore(output).episode_indices())
    assert written == set(range(produced.meta.total_episodes))


def test_preview_states_the_five_figures(tmp_path: Path) -> None:
    """④ The commit preview reports affected count, deleted frames, mapping, stats keys, cost."""
    _root, _output, result = _committed(tmp_path)
    preview = result.preview["output"]

    assert preview.affected_episode_count == 2  # old 2->1 and old 3->2
    assert preview.deleted_frame_count == 4  # episode 1 held four frames
    assert preview.index_mapping == {0: 0, 1: None, 2: 1, 3: 2}
    assert "action" in preview.invalidated_stats_keys
    assert "observation.state" in preview.invalidated_stats_keys
    assert preview.recompute_cost.episodes == 3
    assert preview.recompute_cost.frames == _FRAME_COUNTS[0] + _FRAME_COUNTS[2] + _FRAME_COUNTS[3]


def test_output_loads_once_as_a_dataset(tmp_path: Path) -> None:
    """⑤ The edited dataset loads as a LeRobotDataset with the surviving episode count."""
    _root, output, result = _committed(tmp_path)
    reloaded = LeRobotDataset(result.outputs["output"].repo_id, root=output)
    assert reloaded.meta.total_episodes == 3


def test_original_is_immutable_and_coexists(tmp_path: Path) -> None:
    """⑥ Copy-on-write leaves the original — data and sidecars — beside the new version."""
    root, output, _result = _committed(tmp_path)
    original = LeRobotDataset("synthetic/edit", root=root)
    assert original.meta.total_episodes == 4
    # The original's own sidecars are untouched: the deleted episode 1 still has its label.
    assert set(DatasetStore(root).episode_indices()) == {0, 1, 2, 3}
    assert output.exists() and root.exists()


def test_disk_precheck_requires_room_for_the_coexisting_copy(tmp_path: Path, monkeypatch) -> None:
    """⑥ The engine refuses to start when the filesystem cannot hold both versions."""
    root = tmp_path / "ds"
    build_dataset(root, _FRAME_COUNTS)

    # Enough room: the precheck passes silently.
    disk_precheck(root, tmp_path / "out")

    # Starve the filesystem: the precheck must raise before any write.
    import backend.dataset.edit.engine as engine

    class _Tiny:
        free = 1

    monkeypatch.setattr(engine.shutil, "disk_usage", lambda _path: _Tiny())
    with pytest.raises(engine.CowDiskError):
        engine.disk_precheck(root, tmp_path / "out2")
