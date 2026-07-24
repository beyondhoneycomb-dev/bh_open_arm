"""The commit preview — what an edit will do, computed before it is committed (WP-3D-02).

`02b` §8.2 WP-3D-02 ④ requires a preview that states, before the edit runs, the
"영향 에피소드 수·삭제 프레임 수·인덱스 매핑·무효화 통계 키·재계산 소요". This module
computes exactly those five from the original dataset's metadata and the operation's
parameters alone — it opens no data shard and writes nothing, so a preview is free of
the copy-on-write cost of the edit it describes.

The index mapping and survivor sets come from the operation itself (`expected_survivors`),
so the preview and the later 100% cross-check are derived from one source and cannot
disagree about which episode becomes which.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.dataset.edit.constants import EPISODE_LENGTH_KEY
from backend.dataset.edit.operations import EditOperation


@dataclass(frozen=True)
class RecomputeCost:
    """The work a statistics recompute over an output would traverse.

    An estimate, not a measurement: statistics are aggregated per frame across the
    kept episodes, so the frame and episode counts of the output bound the cost. The
    exact fit is WP-3D-03's; this only sizes it for the operator's pre-commit decision.

    Attributes:
        frames: The number of frames the output keeps.
        episodes: The number of episodes the output keeps.
    """

    frames: int
    episodes: int


@dataclass(frozen=True)
class EditPreview:
    """The pre-commit description of one output dataset.

    Attributes:
        output_name: The output this preview describes (a split name, or the single
            output key).
        affected_episode_count: Surviving episodes whose index changes under the edit.
        deleted_frame_count: Frames in the original not carried into this output.
        index_mapping: Original episode index to its new index, or None when the
            episode is not carried into this output.
        invalidated_stats_keys: The statistics keys this output must recompute; a
            renumber invalidates every aggregate, so all are listed.
        recompute_cost: The estimated recompute work for this output.
    """

    output_name: str
    affected_episode_count: int
    deleted_frame_count: int
    index_mapping: dict[int, int | None]
    invalidated_stats_keys: tuple[str, ...]
    recompute_cost: RecomputeCost


def _stats_keys(dataset: Any) -> tuple[str, ...]:
    """The statistics keys a renumber invalidates, ascending.

    Args:
        dataset: The loaded source `LeRobotDataset`.

    Returns:
        (tuple[str, ...]) The dataset's statistics keys, or its feature keys when no
            statistics are present yet.
    """
    stats = getattr(dataset.meta, "stats", None)
    if stats:
        return tuple(sorted(stats.keys()))
    return tuple(sorted(dataset.meta.features.keys()))


def _episode_length(dataset: Any, episode_index: int) -> int:
    """Return one episode's frame count from the dataset metadata.

    Args:
        dataset: The loaded source `LeRobotDataset`.
        episode_index: The episode index.

    Returns:
        (int) The episode's length in frames.
    """
    return int(dataset.meta.episodes[episode_index][EPISODE_LENGTH_KEY])


def build_preview(dataset: Any, operation: EditOperation) -> dict[str, EditPreview]:
    """Compute the pre-commit preview for every output of an operation.

    Args:
        dataset: The loaded source `LeRobotDataset`, read but not modified.
        operation: The edit operation to preview.

    Returns:
        (dict[str, EditPreview]) Output name to its preview.
    """
    total_episodes = dataset.meta.total_episodes
    total_frames = int(dataset.meta.total_frames)
    stats_keys = _stats_keys(dataset)
    survivors_by_output = operation.expected_survivors(dataset)

    previews: dict[str, EditPreview] = {}
    for output_name, survivors in survivors_by_output.items():
        index_mapping: dict[int, int | None] = dict.fromkeys(range(total_episodes))
        affected = 0
        kept_frames = 0
        for new_index, old_index in enumerate(survivors):
            index_mapping[old_index] = new_index
            kept_frames += _episode_length(dataset, old_index)
            if new_index != old_index:
                affected += 1
        previews[output_name] = EditPreview(
            output_name=output_name,
            affected_episode_count=affected,
            deleted_frame_count=total_frames - kept_frames,
            index_mapping=index_mapping,
            invalidated_stats_keys=stats_keys,
            recompute_cost=RecomputeCost(frames=kept_frames, episodes=len(survivors)),
        )
    return previews
