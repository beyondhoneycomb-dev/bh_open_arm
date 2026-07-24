"""Provenance of a LeRobot-format dataset — native recording vs legacy import.

`FR-DAT-041` requires the two families to be distinguishable and never merged. The
distinction is not a schema detail a reader can infer from bytes: a native recording
and a legacy-imported one can look almost identical, and it is exactly the "almost"
that makes silent merging dangerous. So provenance is carried as an explicit tag on
every artifact the merge guard (`merge_guard.py`) consults.
"""

from __future__ import annotations

from enum import Enum


class DatasetProvenance(Enum):
    """Where a LeRobot-format dataset came from.

    Attributes:
        NATIVE: Recorded by our LeRobot recorder under `CTR-REC@v1` (`WP-3B-11`).
        IMPORTED_LEGACY: Produced by `openarm-dataset-convert --format lerobot_v3.0`
            from a legacy OpenArm dataset (`FR-DAT-040`). Its schema differs subtly
            from a native recording (`FR-DAT-041`) and it must not merge with one.
    """

    NATIVE = "native"
    IMPORTED_LEGACY = "imported_legacy"
