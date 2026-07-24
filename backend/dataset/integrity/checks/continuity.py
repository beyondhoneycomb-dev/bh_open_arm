"""Check 3 — `dataset_from/to_index` is continuous (`02b` §8.2 WP-3D-05).

Every episode owns a half-open row range `[dataset_from_index, dataset_to_index)`
into the packed data parquet. For the packing to be sound the ranges must tile the
table with no gap and no overlap: episode 0 starts at row 0, each episode's range
width equals its declared `length`, each range begins where the previous ended, and
the final range ends at the parquet's row count. A break anywhere means some rows
belong to no episode or to two — a global `index` that resolves to the wrong frame.
"""

from __future__ import annotations

import pyarrow.parquet as pq

from backend.dataset.integrity.constants import CHECK_INDEX_CONTINUITY
from backend.dataset.integrity.dataset import DatasetInventory, InventoryError
from backend.dataset.integrity.report import CheckResult, failed, passed
from backend.dataset.viewer.constants import (
    EPISODE_FROM_INDEX_COLUMN,
    EPISODE_INDEX_COLUMN,
    EPISODE_LENGTH_COLUMN,
    EPISODE_TO_INDEX_COLUMN,
)


def check_index_continuity(inventory: DatasetInventory) -> CheckResult:
    """Verify the episode row ranges tile the data parquet with no gap or overlap.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) PASS when the ranges are continuous and end at the parquet's
            row count; FAIL naming the first discontinuity.
    """
    try:
        rows = inventory.episode_rows()
        data_files = inventory.data_files()
    except InventoryError as bad:
        return failed(CHECK_INDEX_CONTINUITY, f"episode metadata unreadable: {bad}")

    if not rows:
        return failed(CHECK_INDEX_CONTINUITY, "dataset declares no episode metadata")

    expected_from = 0
    for position, row in enumerate(rows):
        index = _int(row.get(EPISODE_INDEX_COLUMN))
        from_index = _int(row.get(EPISODE_FROM_INDEX_COLUMN))
        to_index = _int(row.get(EPISODE_TO_INDEX_COLUMN))
        length = _int(row.get(EPISODE_LENGTH_COLUMN))

        if index != position:
            return failed(
                CHECK_INDEX_CONTINUITY,
                f"episode indices are not 0..N-1 contiguous: position {position} has index {index}",
            )
        if from_index is None or to_index is None:
            return failed(CHECK_INDEX_CONTINUITY, f"episode {index} lacks a dataset_from/to_index")
        if to_index - from_index != length:
            return failed(
                CHECK_INDEX_CONTINUITY,
                f"episode {index} range width {to_index - from_index} != length {length}",
            )
        if from_index != expected_from:
            return failed(
                CHECK_INDEX_CONTINUITY,
                f"episode {index} starts at {from_index}, expected {expected_from} "
                "(gap or overlap in the packed row ranges)",
            )
        expected_from = to_index

    try:
        total_rows = sum(pq.read_metadata(path).num_rows for path in data_files)
    except Exception as bad:  # noqa: BLE001 — an unreadable count is itself a continuity failure
        return failed(CHECK_INDEX_CONTINUITY, f"data parquet row count unreadable: {bad}")

    if expected_from != total_rows:
        return failed(
            CHECK_INDEX_CONTINUITY,
            f"episode ranges cover {expected_from} rows but the data parquet holds {total_rows}",
        )

    return passed(
        CHECK_INDEX_CONTINUITY, f"{len(rows)} episode range(s) tile {total_rows} rows continuously"
    )


def _int(value: object) -> int | None:
    """Coerce a metadata cell to int, or None when it is absent/non-numeric."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
