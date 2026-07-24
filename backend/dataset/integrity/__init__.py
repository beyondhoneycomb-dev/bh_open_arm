"""Dataset integrity verification for the OpenArm training corpus (WP-3D-05).

A dataset is READY to be a training input only when seven checks all pass: parquet
footers are readable, `info.json` agrees with the chunk/file layout, the episode
row ranges are continuous, encoded frame counts match declared lengths, parquet
dtypes match `info.json`, the stats table hashes to its recorded value, and the
dataset carries no aborted-edit `EDIT_INVALID` marker. One failure — or a check
that did not run — makes the dataset INVALID, and INVALID is never exposed to a
trainer (`FR-DAT-051`, `NFR-DAT-005`).

`verify_dataset` returns the full report; `ensure_training_ready` is the interlock
boundary WP-3C-06 (source-delete) consumes. The verifier reads the LeRobot v3.0
layout through the committed WP-3D-01 viewer and hashes stats through the committed
WP-3D-03 routine — it reuses those, it does not fork them.
"""

from __future__ import annotations

from backend.dataset.integrity.bandwidth import (
    dataset_byte_size,
    measure_sequential_read_bandwidth,
    regression_bound_seconds,
    sequential_read_seconds,
    within_regression_bound,
)
from backend.dataset.integrity.constants import (
    CHECK_DTYPE_MATCH,
    CHECK_INDEX_CONTINUITY,
    CHECK_INFO_CHUNK_CONSISTENCY,
    CHECK_NO_EDIT_MARKER,
    CHECK_PARQUET_FOOTER,
    CHECK_STATS_HASH_MATCH,
    CHECK_VIDEO_FRAME_COUNT,
    REQUIRED_CHECKS,
    VERDICT_INVALID,
    VERDICT_READY,
)
from backend.dataset.integrity.dataset import DatasetInventory
from backend.dataset.integrity.report import (
    CheckResult,
    CheckStatus,
    IntegrityError,
    IntegrityReport,
)
from backend.dataset.integrity.verify import (
    ensure_training_ready,
    is_ready,
    verify_dataset,
)

__all__ = [
    "CHECK_DTYPE_MATCH",
    "CHECK_INDEX_CONTINUITY",
    "CHECK_INFO_CHUNK_CONSISTENCY",
    "CHECK_NO_EDIT_MARKER",
    "CHECK_PARQUET_FOOTER",
    "CHECK_STATS_HASH_MATCH",
    "CHECK_VIDEO_FRAME_COUNT",
    "REQUIRED_CHECKS",
    "VERDICT_INVALID",
    "VERDICT_READY",
    "CheckResult",
    "CheckStatus",
    "DatasetInventory",
    "IntegrityError",
    "IntegrityReport",
    "dataset_byte_size",
    "ensure_training_ready",
    "is_ready",
    "measure_sequential_read_bandwidth",
    "regression_bound_seconds",
    "sequential_read_seconds",
    "verify_dataset",
    "within_regression_bound",
]
