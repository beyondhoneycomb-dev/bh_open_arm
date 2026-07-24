"""The eight LeRobot edit operations, wrapped as calls — never re-implemented (WP-3D-02).

`02b` §8.1 WP-3D-02 makes the deliverable "8연산 **호출 제공**(자체 재구현 금지)": this
package provides the *calls* to `lerobot-edit-dataset`'s eight transformation operations
and the policy each one imposes on the copy-on-write engine, and re-implements none of
them. Every `call()` here delegates straight to a `lerobot.datasets` function.

The policy is what the engine needs and the CLI does not surface uniformly:

- `renumbers` — the operation rewrites episode indices, so the sidecar tree must be
  remapped by the 100% content cross-check before the output is valid (`02b` §8.2 ①).
  `delete_episodes` and `split` renumber; the rest preserve episode identity.
- `in_place` — upstream mutates its input directory. `modify_tasks`, `recompute_stats`
  and `reencode` rewrite the dataset they are handed ("upstream `modify_tasks`는
  in-place(파괴적)"): the engine copies first so the original stays immutable
  (FR-DAT-022 = CoW).
- `cross_dataset` — the operation spans multiple datasets. `merge` is delegated to
  WP-3D-06 (병합·분할), whose shape-equality and gain-profile rules govern it; the
  engine refuses to drive it here rather than ship a renumber with no verified remap.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lerobot.datasets import (
    convert_image_to_video_dataset,
    delete_episodes,
    merge_datasets,
    modify_tasks,
    recompute_stats,
    reencode_dataset,
    remove_feature,
    split_dataset,
)

from backend.dataset.edit.constants import SINGLE_OUTPUT_KEY


@dataclass(frozen=True)
class OperationPolicy:
    """How an edit operation interacts with the copy-on-write engine.

    Attributes:
        renumbers: The operation rewrites episode indices; a sidecar remap with the
            100% content cross-check is required before the output is valid.
        in_place: Upstream mutates the dataset it is handed; the engine must copy the
            original first so it stays immutable.
        multi_output: The operation produces more than one dataset (split).
        cross_dataset: The operation spans multiple datasets (merge), delegated to
            WP-3D-06 rather than driven here.
    """

    renumbers: bool
    in_place: bool
    multi_output: bool
    cross_dataset: bool


@dataclass(frozen=True)
class EditContext:
    """The input and output placement one operation call needs.

    Attributes:
        dataset: The source `LeRobotDataset` to operate on — already the copy-on-write
            copy for an in-place operation.
        output_dir: The directory the new dataset(s) are written under.
        repo_id: The output repository id.
    """

    dataset: Any
    output_dir: Path
    repo_id: str


class EditOperation(abc.ABC):
    """One `lerobot-edit-dataset` operation, as a call plus its engine policy.

    Subclasses hold the operation's parameters and delegate `call()` to the matching
    `lerobot.datasets` function. They never re-implement the transformation.
    """

    name: str
    policy: OperationPolicy

    @abc.abstractmethod
    def call(self, context: EditContext) -> dict[str, Any]:
        """Invoke the underlying LeRobot operation and return its output datasets.

        Args:
            context: The source dataset and output placement.

        Returns:
            (dict[str, Any]) Output name to produced `LeRobotDataset`. A single-output
                operation files its result under `SINGLE_OUTPUT_KEY`.
        """

    def expected_survivors(self, dataset: Any) -> dict[str, list[int]]:
        """The original episode indices each output keeps, in produced order.

        This is the ground truth the content cross-check verifies the produced
        dataset against (`02b` §8.2 WP-3D-02 ①): produced episode *j* must carry the
        content of `expected_survivors()[output][j]`. Only renumbering operations
        override it; identity-preserving operations keep every episode in place.

        Args:
            dataset: The loaded source `LeRobotDataset`.

        Returns:
            (dict[str, list[int]]) Output name to surviving original indices, ordered.
        """
        return {SINGLE_OUTPUT_KEY: list(range(dataset.meta.total_episodes))}


@dataclass(frozen=True)
class DeleteEpisodes(EditOperation):
    """Delete episodes, renumbering the survivors — calls `delete_episodes`.

    Attributes:
        episode_indices: The original episode indices to remove.
    """

    episode_indices: tuple[int, ...]

    name = "delete_episodes"
    policy = OperationPolicy(
        renumbers=True, in_place=False, multi_output=False, cross_dataset=False
    )

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `delete_episodes` into the output directory."""
        produced = delete_episodes(
            context.dataset,
            episode_indices=list(self.episode_indices),
            output_dir=context.output_dir,
            repo_id=context.repo_id,
        )
        return {SINGLE_OUTPUT_KEY: produced}

    def expected_survivors(self, dataset: Any) -> dict[str, list[int]]:
        """Every original index except the deleted ones, ascending — LeRobot's order."""
        deleted = set(self.episode_indices)
        survivors = [i for i in range(dataset.meta.total_episodes) if i not in deleted]
        return {SINGLE_OUTPUT_KEY: survivors}


@dataclass(frozen=True)
class SplitDataset(EditOperation):
    """Split into named subsets, each renumbered from zero — calls `split_dataset`.

    Only explicit episode-index splits are driven here: the survivor set of a
    fraction split is resolved inside LeRobot, so verifying the remap against it would
    require re-deriving LeRobot's own partition, and fraction splits are WP-3D-06's
    (분할) responsibility.

    Attributes:
        splits: Split name to the original episode indices it keeps.
    """

    splits: Mapping[str, Sequence[int]]

    name = "split"
    policy = OperationPolicy(renumbers=True, in_place=False, multi_output=True, cross_dataset=False)

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `split_dataset` with explicit index lists into the output directory."""
        splits: dict[str, list[int]] = {
            name: list(indices) for name, indices in self.splits.items()
        }
        return dict(split_dataset(context.dataset, splits=splits, output_dir=context.output_dir))

    def expected_survivors(self, _dataset: Any) -> dict[str, list[int]]:
        """Each split's declared episodes, ascending — LeRobot renumbers them from zero.

        The survivor set is the split's own index list; the dataset is not consulted,
        because a split selects rather than derives its members.
        """
        return {name: sorted(indices) for name, indices in self.splits.items()}


@dataclass(frozen=True)
class ModifyTasks(EditOperation):
    """Relabel episode tasks — calls `modify_tasks`, which mutates its input in place.

    The in-place policy is the whole reason CoW exists here: called directly on the
    original it overwrites it (`02b` §8.2 WP-3D-02). The engine copies first, so this
    runs against the copy and the original is untouched. Episode indices are preserved.

    Attributes:
        new_task: A single task applied to every episode, or None.
        episode_tasks: Per-episode task overrides keyed by episode index, or None.
    """

    new_task: str | None
    episode_tasks: Mapping[int, str] | None

    name = "modify_tasks"
    policy = OperationPolicy(
        renumbers=False, in_place=True, multi_output=False, cross_dataset=False
    )

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `modify_tasks` on the (already copied) dataset, mutating it in place."""
        episode_tasks = dict(self.episode_tasks) if self.episode_tasks is not None else None
        produced = modify_tasks(
            context.dataset, new_task=self.new_task, episode_tasks=episode_tasks
        )
        return {SINGLE_OUTPUT_KEY: produced}


@dataclass(frozen=True)
class RemoveFeature(EditOperation):
    """Drop feature columns into a new dataset — calls `remove_feature`.

    Episode indices are preserved, so the sidecars copy across one-to-one.

    Attributes:
        feature_names: The feature keys to remove.
    """

    feature_names: tuple[str, ...]

    name = "remove_feature"
    policy = OperationPolicy(
        renumbers=False, in_place=False, multi_output=False, cross_dataset=False
    )

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `remove_feature` into the output directory."""
        produced = remove_feature(
            context.dataset,
            feature_names=list(self.feature_names),
            output_dir=context.output_dir,
            repo_id=context.repo_id,
        )
        return {SINGLE_OUTPUT_KEY: produced}


@dataclass(frozen=True)
class RecomputeStats(EditOperation):
    """Recompute dataset statistics into the dataset it is given — calls `recompute_stats`.

    The train-split-only fit and std-floor detection are WP-3D-03's; this only
    provides the CoW-guarded call. `recompute_stats` writes into the dataset it is
    handed, so the engine hands it a copy. Episode indices are preserved.

    Attributes:
        skip_image_video: Whether to skip image/video features when aggregating.
    """

    skip_image_video: bool

    name = "recompute_stats"
    policy = OperationPolicy(
        renumbers=False, in_place=True, multi_output=False, cross_dataset=False
    )

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `recompute_stats` on the (already copied) dataset."""
        recompute_stats(context.dataset, skip_image_video=self.skip_image_video)
        return {SINGLE_OUTPUT_KEY: context.dataset}


@dataclass(frozen=True)
class ReencodeVideos(EditOperation):
    """Re-encode the dataset's videos in place — calls `reencode_dataset`.

    `reencode_dataset` rewrites the videos of the dataset it is given, so the engine
    hands it a copy. Episode indices are preserved.
    """

    name = "reencode_videos"
    policy = OperationPolicy(
        renumbers=False, in_place=True, multi_output=False, cross_dataset=False
    )

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `reencode_dataset` on the (already copied) dataset."""
        reencode_dataset(context.dataset)
        return {SINGLE_OUTPUT_KEY: context.dataset}


@dataclass(frozen=True)
class ConvertImageToVideo(EditOperation):
    """Convert an image dataset to video format — calls `convert_image_to_video_dataset`.

    Episode indices are preserved.
    """

    name = "convert_image_to_video"
    policy = OperationPolicy(
        renumbers=False, in_place=False, multi_output=False, cross_dataset=False
    )

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `convert_image_to_video_dataset` into the output directory."""
        produced = convert_image_to_video_dataset(
            dataset=context.dataset,
            output_dir=context.output_dir,
            repo_id=context.repo_id,
        )
        return {SINGLE_OUTPUT_KEY: produced}


@dataclass(frozen=True)
class MergeDatasets(EditOperation):
    """Merge multiple datasets — the call to `merge_datasets`, delegated to WP-3D-06.

    Merge renumbers by concatenation across source datasets, and its shape-equality
    and gain-profile rules are WP-3D-06's (병합). The call is provided for completeness
    of the eight-operation surface, but the CoW engine refuses to drive it so a
    cross-dataset renumber never ships with an unverified sidecar remap.

    Attributes:
        roots: The source dataset roots to merge, in order.
        repo_ids: The source repository ids, aligned with `roots`.
    """

    roots: tuple[Path, ...]
    repo_ids: tuple[str, ...]

    name = "merge"
    policy = OperationPolicy(renumbers=True, in_place=False, multi_output=False, cross_dataset=True)

    def call(self, context: EditContext) -> dict[str, Any]:
        """Call `merge_datasets` over the source roots into the output directory."""
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        datasets = [
            LeRobotDataset(source_repo_id, root=root)
            for source_repo_id, root in zip(self.repo_ids, self.roots, strict=True)
        ]
        produced = merge_datasets(
            datasets, output_repo_id=context.repo_id, output_dir=context.output_dir
        )
        return {SINGLE_OUTPUT_KEY: produced}


# The eight transformation operations `lerobot-edit-dataset` exposes (its ninth verb,
# `info`, is a read-only report, not an edit). Names match the CLI's operation types.
EDIT_OPERATION_NAMES = (
    "delete_episodes",
    "split",
    "merge",
    "remove_feature",
    "modify_tasks",
    "convert_image_to_video",
    "recompute_stats",
    "reencode_videos",
)
