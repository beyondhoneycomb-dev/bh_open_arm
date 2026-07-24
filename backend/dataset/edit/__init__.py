"""Copy-on-write dataset edit + sidecar remap (WP-3D-02, `02b` §8).

This band edits a recorded LeRobot dataset without ever mutating the original and
without letting a label drift onto the wrong episode. It is built on two rules from
`02b` §8.2 WP-3D-02, and re-implements none of the transformations it applies:

- **The edit is a call, not a rewrite.** The eight `lerobot-edit-dataset` operations
  are invoked through `operations.py`; this package provides the *calls* and the policy
  around them (copy-on-write, verified remap), and leaves the transformation to LeRobot.
- **A renumber remaps the sidecars, or the output is INVALID.** When an operation
  rewrites episode indices, every per-episode quality sidecar (WP-3B-12) is carried to
  its new index by a 100% content cross-check — episode content hash to label reverse
  lookup, no sampling. One episode whose content does not resolve to its expected
  original aborts the edit and marks the output INVALID, because a remap-less renumber
  attaches a label to the wrong episode (the band's FAIL_BLOCKING).

`FR-DAT-022` is resolved here as copy-on-write: the original is immutable, the new
version coexists with it on disk, and the engine refuses to start without room for both.
"""

from __future__ import annotations

from backend.dataset.edit.content_hash import ContentHashError, episode_content_hashes
from backend.dataset.edit.engine import (
    CowDiskError,
    CowInPlaceError,
    DelegatedOperationError,
    EditError,
    EditOutput,
    EditResult,
    RemapMismatchError,
    commit_edit,
    disk_precheck,
)
from backend.dataset.edit.operations import (
    EDIT_OPERATION_NAMES,
    ConvertImageToVideo,
    DeleteEpisodes,
    EditContext,
    EditOperation,
    MergeDatasets,
    ModifyTasks,
    OperationPolicy,
    RecomputeStats,
    ReencodeVideos,
    RemoveFeature,
    SplitDataset,
)
from backend.dataset.edit.preview import EditPreview, RecomputeCost, build_preview
from backend.dataset.edit.remap import (
    Mismatch,
    RemapApplyError,
    RemapResult,
    apply_remap,
    copy_sidecars_identity,
    resolve_remap,
)

__all__ = [
    "EDIT_OPERATION_NAMES",
    "ContentHashError",
    "ConvertImageToVideo",
    "CowDiskError",
    "CowInPlaceError",
    "DeleteEpisodes",
    "DelegatedOperationError",
    "EditContext",
    "EditError",
    "EditOperation",
    "EditOutput",
    "EditPreview",
    "EditResult",
    "MergeDatasets",
    "Mismatch",
    "ModifyTasks",
    "OperationPolicy",
    "RecomputeCost",
    "RecomputeStats",
    "ReencodeVideos",
    "RemapApplyError",
    "RemapMismatchError",
    "RemapResult",
    "RemoveFeature",
    "SplitDataset",
    "apply_remap",
    "build_preview",
    "commit_edit",
    "copy_sidecars_identity",
    "disk_precheck",
    "episode_content_hashes",
    "resolve_remap",
]
