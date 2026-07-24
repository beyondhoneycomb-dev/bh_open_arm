"""The seven dataset integrity checks (`02b` §8.2 WP-3D-05).

Each check is a function `(DatasetInventory) -> CheckResult`. They are independent
so one injected defect fails its own check without masking the others, and none of
them raises: an unexpected error inside a check is a FAIL, never a crash of the
verifier, because a verifier that dies on a corrupt dataset would leave that
dataset un-judged rather than INVALID.
"""

from __future__ import annotations

from backend.dataset.integrity.checks.consistency import check_info_chunk_consistency
from backend.dataset.integrity.checks.continuity import check_index_continuity
from backend.dataset.integrity.checks.dtypes import check_dtype_match
from backend.dataset.integrity.checks.edit_marker import check_no_edit_invalid_marker
from backend.dataset.integrity.checks.footer import check_parquet_footer
from backend.dataset.integrity.checks.frames import check_video_frame_count
from backend.dataset.integrity.checks.statshash import check_stats_hash_match

# The checks in the order the report presents them; the same set as
# `constants.REQUIRED_CHECKS`, resolved to callables.
ALL_CHECKS = (
    check_parquet_footer,
    check_info_chunk_consistency,
    check_index_continuity,
    check_video_frame_count,
    check_dtype_match,
    check_stats_hash_match,
    check_no_edit_invalid_marker,
)

__all__ = [
    "ALL_CHECKS",
    "check_info_chunk_consistency",
    "check_index_continuity",
    "check_dtype_match",
    "check_no_edit_invalid_marker",
    "check_parquet_footer",
    "check_video_frame_count",
    "check_stats_hash_match",
]
