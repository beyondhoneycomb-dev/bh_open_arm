"""WP-3D-02 — modify_tasks is in-place upstream, so CoW copies first and keeps the original.

`02b` §8.2 WP-3D-02: "upstream `modify_tasks`는 in-place(파괴적)이므로 그대로 호출하면
정책이 깨진다". The engine copies the original, mutates the copy, and leaves the original's
tasks and sidecars intact. modify_tasks does not renumber, so the sidecars carry across at
the same indices.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.edit import ModifyTasks, commit_edit
from backend.recorder.quality.label import Verdict
from backend.recorder.quality.store import DatasetStore
from tests.wp3d02.support import build_dataset, write_labels

_FRAME_COUNTS = (3, 4, 5)
_VERDICTS = (Verdict.SUCCESS, Verdict.FAIL, Verdict.SUCCESS)
_NEW_TASK = "pick up the cube and place it"


def _episode_tasks(root: Path, repo_id: str, episode_index: int) -> list[str]:
    """Read one episode's task list from a dataset's metadata."""
    dataset = LeRobotDataset(repo_id, root=root)
    return list(dataset.meta.episodes[episode_index]["tasks"])


def test_modify_tasks_mutates_the_copy_not_the_original(tmp_path: Path) -> None:
    """The copy carries the new task; the original's tasks are unchanged."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS)
    write_labels(root, _VERDICTS)
    output = tmp_path / "ds_relabeled"

    result = commit_edit(root, stamped, ModifyTasks(new_task=_NEW_TASK, episode_tasks=None), output)

    out = result.outputs["output"]
    assert _episode_tasks(out.root, out.repo_id, 0) == [_NEW_TASK]
    # The original still names its original task — copy-on-write did not touch it.
    assert _episode_tasks(root, "synthetic/edit", 0) == ["task_0"]


def test_modify_tasks_carries_sidecars_unchanged(tmp_path: Path) -> None:
    """No renumber: every sidecar carries across at the same index with the same verdict."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS)
    write_labels(root, _VERDICTS)
    output = tmp_path / "ds_relabeled"

    result = commit_edit(root, stamped, ModifyTasks(new_task=_NEW_TASK, episode_tasks=None), output)

    store = DatasetStore(result.outputs["output"].root)
    assert set(store.episode_indices()) == {0, 1, 2}
    for index, verdict in enumerate(_VERDICTS):
        body = json.loads(store.sidecar_path(index).read_text(encoding="utf-8"))
        assert body["episode_index"] == index
        assert body["label"]["manual"]["verdict"] == verdict.value
    assert result.outputs["output"].episode_mapping == {0: 0, 1: 1, 2: 2}
