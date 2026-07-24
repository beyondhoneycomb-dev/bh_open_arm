"""Ratio and index dataset splits, on episode boundaries only (WP-3D-06, `02b` §8.2).

`FR-DAT-046`/`047` and `02b` §8.2 WP-3D-06 ③: a dataset splits by ratio
(`{"train": 0.8, "val": 0.2}`) or by explicit episode index
(`{"train": [0,1,2,3], "val": [4,5]}`), and a split happens on episode boundaries only —
a single episode's frames never straddle two splits.

The episode-boundary guarantee is structural, not checked after the fact: both split
forms select whole *episode indices*, and the split itself is the committed WP-3D-02
`SplitDataset` edit (imported, not re-implemented), which renumbers each output from zero
and remaps its sidecars by the 100% content cross-check. A ratio is turned into a whole-
episode index partition here — largest-remainder allocation over episode counts — so the
ratio path is the index path with a computed partition, and a frame can no more cross a
split than an episode can be half-selected.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from backend.dataset.edit import EditResult, SplitDataset, commit_edit
from backend.dataset.merge.constants import SPLIT_RATIO_SUM, SPLIT_RATIO_TOLERANCE


class SplitError(ValueError):
    """Raised when a split is not a whole-episode partition of the dataset.

    Covers a ratio set that does not sum to one, a ratio too small to claim a whole
    episode (which would need a fractional episode), an index split that overlaps,
    omits, or ranges outside the dataset's episodes, or a split of fewer than two parts.
    Every case would break the episode-boundary rule (`02b` §8.2 WP-3D-06 ③), so it is
    refused before any bytes are written.
    """


def _total_episodes(repo_id: str, root: Path) -> int:
    """Return a dataset's episode count from its metadata.

    Args:
        repo_id: The dataset repository id.
        root: The dataset root.

    Returns:
        (int) The total episode count.
    """
    return int(LeRobotDataset(repo_id, root=root).meta.total_episodes)


def plan_ratio_split(total_episodes: int, ratios: Mapping[str, float]) -> dict[str, list[int]]:
    """Turn split ratios into a contiguous whole-episode index partition.

    Uses largest-remainder allocation so the per-split episode counts sum exactly to the
    dataset's episode count with no episode left unassigned or double-assigned, then lays
    the splits out over contiguous episode-index blocks in declaration order. Because the
    unit of allocation is a whole episode, no frame can cross a split (`FR-DAT-047`).

    Args:
        total_episodes: The dataset's episode count.
        ratios: Split name to its fraction; at least two, each positive, summing to one.

    Returns:
        (dict[str, list[int]]) Split name to the contiguous episode indices it keeps.

    Raises:
        SplitError: On fewer than two splits, a non-positive ratio, a sum that is not
            one, or a ratio too small to claim a whole episode (an empty split).
    """
    if len(ratios) < 2:
        raise SplitError(f"a split needs at least two parts, got {len(ratios)}")
    if any(fraction <= 0.0 for fraction in ratios.values()):
        raise SplitError(f"every split ratio must be positive, got {dict(ratios)}")
    total_ratio = math.fsum(ratios.values())
    if abs(total_ratio - SPLIT_RATIO_SUM) > SPLIT_RATIO_TOLERANCE:
        raise SplitError(
            f"split ratios must sum to {SPLIT_RATIO_SUM}, got {total_ratio} for {dict(ratios)}"
        )
    if total_episodes < len(ratios):
        raise SplitError(
            f"cannot split {total_episodes} episode(s) into {len(ratios)} parts on episode "
            "boundaries without an empty split"
        )

    order = list(ratios)
    counts = {name: int(math.floor(ratios[name] * total_episodes)) for name in order}
    leftover = total_episodes - sum(counts.values())
    remainders = sorted(
        order,
        key=lambda name: (-(ratios[name] * total_episodes - counts[name]), order.index(name)),
    )
    for name in remainders[:leftover]:
        counts[name] += 1

    empty = [name for name in order if counts[name] == 0]
    if empty:
        raise SplitError(
            f"splits {empty} would be empty at {total_episodes} episode(s); a ratio split "
            "cannot claim a fraction of an episode (episode-boundary rule)"
        )

    partition: dict[str, list[int]] = {}
    start = 0
    for name in order:
        partition[name] = list(range(start, start + counts[name]))
        start += counts[name]
    return partition


def validate_index_split(total_episodes: int, splits: Mapping[str, Sequence[int]]) -> None:
    """Refuse an index split that is not a whole-episode partition of the dataset.

    Args:
        total_episodes: The dataset's episode count.
        splits: Split name to the episode indices it claims.

    Raises:
        SplitError: On fewer than two parts, an out-of-range or negative index, an
            episode claimed by two splits, or an episode no split claims.
    """
    if len(splits) < 2:
        raise SplitError(f"a split needs at least two parts, got {len(splits)}")
    seen: dict[int, str] = {}
    for name, indices in splits.items():
        for index in indices:
            if not 0 <= index < total_episodes:
                raise SplitError(
                    f"split {name!r} references episode {index}, outside [0, {total_episodes})"
                )
            if index in seen:
                raise SplitError(
                    f"episode {index} is claimed by both {seen[index]!r} and {name!r}; an "
                    "episode cannot cross a split (episode-boundary rule)"
                )
            seen[index] = name
    missing = sorted(set(range(total_episodes)) - set(seen))
    if missing:
        raise SplitError(
            f"episodes {missing} are in no split; a split must partition every episode"
        )


def split_by_index(
    root: Path, repo_id: str, splits: Mapping[str, Sequence[int]], output_dir: Path
) -> EditResult:
    """Split a dataset by explicit episode indices, on episode boundaries only.

    Validates the split is a whole-episode partition, then delegates to the committed
    `SplitDataset` edit under copy-on-write, which renumbers each output from zero and
    remaps its sidecars by the 100% content cross-check.

    Args:
        root: The dataset root, left immutable by the copy-on-write edit.
        repo_id: The dataset repository id.
        splits: Split name to the episode indices it keeps.
        output_dir: The base directory the split outputs are written under.

    Returns:
        (EditResult) The per-split preview and committed outputs, from the edit engine.

    Raises:
        SplitError: When the split is not a whole-episode partition.
    """
    validate_index_split(_total_episodes(repo_id, root), splits)
    operation = SplitDataset(splits={name: list(indices) for name, indices in splits.items()})
    return commit_edit(root, repo_id, operation, output_dir)


def split_by_ratio(
    root: Path, repo_id: str, ratios: Mapping[str, float], output_dir: Path
) -> EditResult:
    """Split a dataset by ratio, resolved to a whole-episode partition first.

    The ratios are turned into a contiguous episode-index partition (`plan_ratio_split`)
    and then run through `split_by_index`, so the ratio path inherits the same episode-
    boundary guarantee and the same verified sidecar remap.

    Args:
        root: The dataset root, left immutable.
        repo_id: The dataset repository id.
        ratios: Split name to its fraction; at least two, positive, summing to one.
        output_dir: The base directory the split outputs are written under.

    Returns:
        (EditResult) The per-split preview and committed outputs.

    Raises:
        SplitError: When the ratios do not resolve to a whole-episode partition.
    """
    partition = plan_ratio_split(_total_episodes(repo_id, root), ratios)
    return split_by_index(root, repo_id, partition, output_dir)
