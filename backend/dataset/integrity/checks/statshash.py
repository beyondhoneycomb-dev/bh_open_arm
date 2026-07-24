"""Check 6 — the stats table hashes to the recorded value (`02b` §8.2 WP-3D-05).

The normalization statistics a checkpoint trained under are content-hashed and the
digest is stamped into the dataset (`info.json`) and the lineage record (WP-3D-03 ④,
WP-3D-04). This check recomputes the hash of the on-disk `meta/stats.json` with the
committed hashing routine — it does not reimplement the digest — and compares it to
the recorded value. A mismatch means the stats table was edited after the hash was
stamped, so a model would normalise with statistics different from the ones it was
trained under.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from backend.dataset.integrity.constants import CHECK_STATS_HASH_MATCH
from backend.dataset.integrity.dataset import DatasetInventory, InventoryError
from backend.dataset.integrity.report import CheckResult, failed, passed
from backend.dataset.stats.hashing import stats_content_hash


def check_stats_hash_match(inventory: DatasetInventory) -> CheckResult:
    """Verify `meta/stats.json` hashes to the dataset's recorded stats hash.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) PASS when the recomputed hash equals the recorded one; FAIL
            when the sidecar is missing/unreadable, no hash is recorded, or they
            disagree.
    """
    recorded = inventory.recorded_stats_hash
    if not recorded:
        return failed(
            CHECK_STATS_HASH_MATCH,
            "no stats content hash recorded (info.json stats_content_hash absent)",
        )

    try:
        table = inventory.load_stats_table()
    except InventoryError as bad:
        return failed(CHECK_STATS_HASH_MATCH, str(bad))

    try:
        # stats_content_hash casts each metric with np.asarray, so a JSON list table
        # is a valid input despite the ndarray-typed signature.
        actual = stats_content_hash(cast("Mapping[str, Mapping[str, Any]]", table))
    except Exception as bad:  # noqa: BLE001 — a malformed stats table cannot be certified
        return failed(CHECK_STATS_HASH_MATCH, f"stats table could not be hashed: {bad}")

    if actual != recorded:
        return failed(
            CHECK_STATS_HASH_MATCH,
            f"stats hash mismatch: recorded {recorded}, meta/stats.json hashes to {actual}",
        )
    return passed(CHECK_STATS_HASH_MATCH, "stats table matches the recorded content hash")
