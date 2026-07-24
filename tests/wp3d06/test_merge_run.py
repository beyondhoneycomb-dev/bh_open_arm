"""WP-3D-06 — the verified merge run end to end on a real on-disk dataset.

Covers the happy path (compatible schema + same gain merges, and each source's sidecar
lands on the right merged episode) and every refusal that runs here: the 24-vs-8 shape
divergence, a gain-profile mismatch, and a gain-tagless source — each refused at preflight
before any bytes are written (`02b` §8.2 WP-3D-06 ①②).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.merge import (
    GainProfileMismatchError,
    GainTagMissingError,
    MergeOutputExistsError,
    MergeSchemaError,
    MergeSource,
    merge_datasets_verified,
)
from backend.dataset.merge.gain import GainProfile, read_gain_profile
from backend.recorder.quality.label import Verdict
from backend.recorder.quality.store import DatasetStore
from contracts.recorder import RecorderConfig
from tests.wp3d06.support import DEFAULT_GAIN, build_dataset, set_robot_type, tag_gain, write_labels

_STIFF = GainProfile(
    profile_id="stiff",
    kp=(230.0, 230.0, 190.0, 190.0, 30.0, 30.0, 30.0, 10.0),
    kd=(2.7, 2.7, 2.2, 2.2, 1.5, 1.5, 1.5, 0.2),
)


def _verdict_at(root: Path, index: int) -> str:
    """Read the manual verdict of a merged sidecar at a merged episode index."""
    body = json.loads(DatasetStore(root).sidecar_path(index).read_text(encoding="utf-8"))
    return str(body["label"]["manual"]["verdict"])


def _make_source(root: Path, frame_counts: tuple[int, ...], repo_id: str, base_offset: float):
    """Build a tagged, labelled merge source with the default compatible config."""
    stamped = build_dataset(root, frame_counts, repo_id=repo_id, base_offset=base_offset)
    tag_gain(root)
    verdicts = tuple(
        Verdict.SUCCESS if index % 2 == 0 else Verdict.FAIL for index in range(len(frame_counts))
    )
    write_labels(root, verdicts)
    return MergeSource(repo_id=stamped, root=root)


def test_merge_happy_path_remaps_each_source_sidecar(tmp_path: Path) -> None:
    """Compatible + same-gain sources merge; each sidecar lands on its merged episode."""
    a = _make_source(tmp_path / "a", (3, 4), "synthetic/a", base_offset=0.0)
    b = _make_source(tmp_path / "b", (5,), "synthetic/b", base_offset=500_000.0)
    out = tmp_path / "merged"

    result = merge_datasets_verified([a, b], "synthetic/merged", out)

    assert LeRobotDataset(result.repo_id, root=result.root).meta.total_episodes == 3
    # A's episodes 0,1 land at merged 0,1; B's episode 0 lands at merged 2.
    assert result.episode_origin[0].source_episode == 0
    assert result.episode_origin[1].source_episode == 1
    assert result.episode_origin[2].source_repo_id == b.repo_id
    assert result.remapped_sidecars == (0, 1, 2)
    # A0->SUCCESS, A1->FAIL, B0->SUCCESS carried to the merged indices.
    assert _verdict_at(result.root, 0) == Verdict.SUCCESS.value
    assert _verdict_at(result.root, 1) == Verdict.FAIL.value
    assert _verdict_at(result.root, 2) == Verdict.SUCCESS.value
    # The merged output is stamped with the shared gain profile.
    assert read_gain_profile(result.repo_id, result.root) == DEFAULT_GAIN


def test_existing_output_refused(tmp_path: Path) -> None:
    """A pre-existing output path is refused (copy-on-write forbids overwriting)."""
    a = _make_source(tmp_path / "a", (2,), "synthetic/a", base_offset=0.0)
    b = _make_source(tmp_path / "b", (2,), "synthetic/b", base_offset=500_000.0)
    out = tmp_path / "merged"
    out.mkdir()
    with pytest.raises(MergeOutputExistsError):
        merge_datasets_verified([a, b], "synthetic/merged", out)


def test_state_shape_divergence_refused_before_write(tmp_path: Path) -> None:
    """A 48-dim and a 16-dim dataset are refused, and nothing is written."""
    a = _make_source(tmp_path / "a", (2,), "synthetic/a", base_offset=0.0)
    root_b = tmp_path / "b"
    stamped_b = build_dataset(
        root_b,
        (2,),
        repo_id="synthetic/b",
        config=RecorderConfig(bimanual=True, use_velocity_and_torque=False),
        base_offset=500_000.0,
    )
    tag_gain(root_b)
    b = MergeSource(repo_id=stamped_b, root=root_b)
    out = tmp_path / "merged"
    with pytest.raises(MergeSchemaError, match="use_velocity_and_torque"):
        merge_datasets_verified([a, b], "synthetic/merged", out)
    assert not out.exists()


def test_robot_type_divergence_refused(tmp_path: Path) -> None:
    """A differing robot_type is refused before any write."""
    a = _make_source(tmp_path / "a", (2,), "synthetic/a", base_offset=0.0)
    b = _make_source(tmp_path / "b", (2,), "synthetic/b", base_offset=500_000.0)
    set_robot_type(b.root, "openarm_bimanual")
    out = tmp_path / "merged"
    with pytest.raises(MergeSchemaError, match="robot_type"):
        merge_datasets_verified([a, b], "synthetic/merged", out)
    assert not out.exists()


def test_gain_mismatch_blocked(tmp_path: Path) -> None:
    """Two datasets under different gain profiles are blocked from merging."""
    a = _make_source(tmp_path / "a", (2,), "synthetic/a", base_offset=0.0)
    root_b = tmp_path / "b"
    stamped_b = build_dataset(root_b, (2,), repo_id="synthetic/b", base_offset=500_000.0)
    tag_gain(root_b, _STIFF)
    b = MergeSource(repo_id=stamped_b, root=root_b)
    out = tmp_path / "merged"
    with pytest.raises(GainProfileMismatchError):
        merge_datasets_verified([a, b], "synthetic/merged", out)
    assert not out.exists()


def test_gain_tagless_is_fail_blocking(tmp_path: Path) -> None:
    """A source with no gain tag is FAIL_BLOCKING and refuses the merge."""
    a = _make_source(tmp_path / "a", (2,), "synthetic/a", base_offset=0.0)
    root_b = tmp_path / "b"
    stamped_b = build_dataset(root_b, (2,), repo_id="synthetic/b", base_offset=500_000.0)
    # b is deliberately left untagged.
    b = MergeSource(repo_id=stamped_b, root=root_b)
    out = tmp_path / "merged"
    with pytest.raises(GainTagMissingError, match="FAIL_BLOCKING"):
        merge_datasets_verified([a, b], "synthetic/merged", out)
    assert not out.exists()
