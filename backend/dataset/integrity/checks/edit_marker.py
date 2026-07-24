"""Check 7 — the dataset carries no aborted-edit sentinel (`02b` §8.2 WP-3D-05).

The CoW edit engine (WP-3D-02) and the merge band (WP-3D-06) write
`meta/EDIT_INVALID.json` into an output whose sidecar remap failed its 100% content
cross-check. That output is structurally whole — parquet, video and stats all parse
— but its label sidecars point at the wrong episodes, the exact FAIL_BLOCKING the
marker exists to signal. The other six checks never read sidecars, so this is the
one check that keeps the marker load-bearing: a dataset wearing it is INVALID and is
never handed to a trainer, however intact the rest of the tree looks.

The marker name is imported from the edit band so both writers and this reader share
one sentinel definition (`06` §5.6, consumed as a sibling constant, not redefined).
"""

from __future__ import annotations

from backend.dataset.edit.constants import INVALID_MARKER_NAME
from backend.dataset.integrity.constants import CHECK_NO_EDIT_MARKER
from backend.dataset.integrity.dataset import DatasetInventory
from backend.dataset.integrity.report import CheckResult, failed, passed


def check_no_edit_invalid_marker(inventory: DatasetInventory) -> CheckResult:
    """Fail when the dataset carries the aborted-edit `EDIT_INVALID` marker.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) FAIL when `meta/EDIT_INVALID.json` is present (an aborted edit
            or merge whose sidecar remap did not verify); PASS when it is absent.
    """
    marker = inventory.root / INVALID_MARKER_NAME
    if marker.is_file():
        return failed(
            CHECK_NO_EDIT_MARKER,
            f"{marker} present: an aborted edit/merge left this dataset's labels unremapped",
        )
    return passed(CHECK_NO_EDIT_MARKER, "no aborted-edit marker present")
