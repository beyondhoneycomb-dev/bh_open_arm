"""WP-3D-06 ③ — ratio and index splits run on episode boundaries, remap sidecars.

The split execution delegates to the committed `SplitDataset` copy-on-write edit, so the
sidecar remap is the same 100% content cross-check a renumber uses; these tests confirm
the split path drives it and that a whole-episode partition results (`FR-DAT-046`/`047`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.merge import split_by_index, split_by_ratio
from backend.recorder.quality.label import Verdict
from backend.recorder.quality.store import DatasetStore
from tests.wp3d06.support import build_dataset, write_labels

_FRAME_COUNTS = (3, 4, 5, 6)
_VERDICTS = (Verdict.SUCCESS, Verdict.FAIL, Verdict.SUCCESS, Verdict.FAIL)


def _verdict_at(root: Path, index: int) -> str:
    """Read the manual verdict of a remapped sidecar at an episode index."""
    body = json.loads(DatasetStore(root).sidecar_path(index).read_text(encoding="utf-8"))
    return str(body["label"]["manual"]["verdict"])


def test_index_split_runs_and_remaps(tmp_path: Path) -> None:
    """An index split renumbers each output from zero and carries the right sidecars."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS, repo_id="synthetic/split")
    write_labels(root, _VERDICTS)

    result = split_by_index(root, stamped, {"train": [0, 1, 2], "val": [3]}, tmp_path / "out")

    train = result.outputs["train"]
    val = result.outputs["val"]
    assert train.episode_mapping == {0: 0, 1: 1, 2: 2}
    assert val.episode_mapping == {0: 3}
    assert _verdict_at(val.root, 0) == Verdict.FAIL.value  # old episode 3 -> FAIL
    # The original is untouched by the copy-on-write split.
    assert LeRobotDataset(stamped, root=root).meta.total_episodes == 4
    assert LeRobotDataset(train.repo_id, root=train.root).meta.total_episodes == 3
    assert LeRobotDataset(val.repo_id, root=val.root).meta.total_episodes == 1


def test_ratio_split_runs_on_episode_boundaries(tmp_path: Path) -> None:
    """A 0.75/0.25 ratio split of 4 episodes yields whole-episode outputs summing to 4."""
    root = tmp_path / "ds"
    stamped = build_dataset(root, _FRAME_COUNTS, repo_id="synthetic/split")
    write_labels(root, _VERDICTS)

    result = split_by_ratio(root, stamped, {"train": 0.75, "val": 0.25}, tmp_path / "out")

    train = result.outputs["train"]
    val = result.outputs["val"]
    train_count = LeRobotDataset(train.repo_id, root=train.root).meta.total_episodes
    val_count = LeRobotDataset(val.repo_id, root=val.root).meta.total_episodes
    assert train_count == 3
    assert val_count == 1
    # The whole-episode partition covers every original episode exactly once.
    assert train_count + val_count == 4
    assert val.episode_mapping == {0: 3}
