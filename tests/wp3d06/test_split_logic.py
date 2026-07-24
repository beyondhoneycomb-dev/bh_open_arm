"""WP-3D-06 ③ — split planning and validation are whole-episode only.

`FR-DAT-046`/`047` / `02b` §8.2 WP-3D-06 ③: ratio and index splits partition on episode
boundaries. These are the pure planning/validation checks; the on-disk execution (which
delegates to the committed `SplitDataset` edit) is exercised in `test_split_run`.
"""

from __future__ import annotations

import pytest

from backend.dataset.merge.split import SplitError, plan_ratio_split, validate_index_split


def test_ratio_split_partitions_all_episodes() -> None:
    """An 80/20 split of 10 episodes assigns contiguous whole-episode blocks covering all."""
    partition = plan_ratio_split(10, {"train": 0.8, "val": 0.2})
    assert partition == {"train": list(range(8)), "val": [8, 9]}


def test_ratio_split_uses_largest_remainder() -> None:
    """A split that does not divide evenly still covers every episode exactly once."""
    partition = plan_ratio_split(7, {"train": 0.7, "val": 0.3})
    covered = sorted(index for indices in partition.values() for index in indices)
    assert covered == list(range(7))
    assert all(partition.values())  # no empty split


def test_ratio_sum_not_one_refused() -> None:
    """Ratios that do not sum to one leave episodes unassigned and are refused."""
    with pytest.raises(SplitError, match="sum to"):
        plan_ratio_split(10, {"train": 0.8, "val": 0.1})


def test_ratio_too_fine_for_episode_count_refused() -> None:
    """A ratio that rounds to zero episodes cannot claim a fraction of an episode."""
    with pytest.raises(SplitError, match="empty split|without an empty split"):
        plan_ratio_split(2, {"train": 0.8, "val": 0.1, "test": 0.1})


def test_index_split_valid_partition_accepted() -> None:
    """A partition covering every episode once passes validation."""
    validate_index_split(6, {"train": [0, 1, 2, 3], "val": [4, 5]})


def test_index_split_overlap_refused() -> None:
    """An episode claimed by two splits would cross a split boundary and is refused."""
    with pytest.raises(SplitError, match="claimed by both"):
        validate_index_split(6, {"train": [0, 1, 2, 3], "val": [3, 4, 5]})


def test_index_split_missing_episode_refused() -> None:
    """An episode in no split means the split is not a partition and is refused."""
    with pytest.raises(SplitError, match="in no split"):
        validate_index_split(6, {"train": [0, 1, 2], "val": [3, 4]})


def test_index_split_out_of_range_refused() -> None:
    """An index outside the dataset's episodes is refused."""
    with pytest.raises(SplitError, match="outside"):
        validate_index_split(4, {"train": [0, 1], "val": [2, 3, 4]})


def test_single_part_split_refused() -> None:
    """A split of one part is not a split."""
    with pytest.raises(SplitError, match="at least two"):
        plan_ratio_split(10, {"train": 1.0})
