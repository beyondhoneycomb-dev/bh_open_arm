"""WP-3D-02 — split renumbers each output from zero, and remaps each output's sidecars.

A split is the multi-output renumber: every subset is renumbered from zero, so each
output's sidecars must be cross-checked and remapped independently (`02b` §8.2 ①). Only
explicit episode-index splits are driven here; a fraction split is WP-3D-06's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.edit import SplitDataset, commit_edit
from backend.recorder.quality.label import Verdict
from backend.recorder.quality.store import DatasetStore
from tests.wp3d02.support import build_dataset, write_labels

_FRAME_COUNTS = (3, 4, 5, 6)
_VERDICTS = (Verdict.SUCCESS, Verdict.FAIL, Verdict.SUCCESS, Verdict.FAIL)


def _verdict_at(root: Path, index: int) -> str:
    """Read the manual verdict of a remapped sidecar at an index."""
    body = json.loads(DatasetStore(root).sidecar_path(index).read_text(encoding="utf-8"))
    return body["label"]["manual"]["verdict"]


def test_split_remaps_each_output_independently(tmp_path: Path) -> None:
    """① Each split renumbers from zero and its sidecars carry the right episode's label."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS)
    write_labels(root, _VERDICTS)
    base = tmp_path / "splits"

    result = commit_edit(root, stamped, SplitDataset(splits={"train": [0, 1, 2], "val": [3]}), base)

    train = result.outputs["train"]
    val = result.outputs["val"]
    assert train.episode_mapping == {0: 0, 1: 1, 2: 2}
    assert val.episode_mapping == {0: 3}

    # train keeps old 0,1,2 -> SUCCESS, FAIL, SUCCESS; val's single episode is old 3 -> FAIL.
    assert _verdict_at(train.root, 0) == Verdict.SUCCESS.value
    assert _verdict_at(train.root, 1) == Verdict.FAIL.value
    assert _verdict_at(train.root, 2) == Verdict.SUCCESS.value
    assert _verdict_at(val.root, 0) == Verdict.FAIL.value

    # Both outputs load, and the original is untouched (copy-on-write).
    assert LeRobotDataset(train.repo_id, root=train.root).meta.total_episodes == 3
    assert LeRobotDataset(val.repo_id, root=val.root).meta.total_episodes == 1
    assert LeRobotDataset("synthetic/edit", root=root).meta.total_episodes == 4


def test_split_val_episode_is_reported_affected(tmp_path: Path) -> None:
    """④ The preview marks the val episode affected — old index 3 becomes new index 0."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS)
    write_labels(root, _VERDICTS)

    result = commit_edit(
        root, stamped, SplitDataset(splits={"train": [0, 1, 2], "val": [3]}), tmp_path / "splits"
    )
    assert result.preview["train"].affected_episode_count == 0
    assert result.preview["val"].affected_episode_count == 1
    assert result.preview["val"].index_mapping[3] == 0
