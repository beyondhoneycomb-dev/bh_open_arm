"""Merge, split and train/val for recorded datasets (WP-3D-06, `02b` §8).

This band answers four questions with a refusal when the answer is unsafe (`02b` §8.2
WP-3D-06, `FR-DAT-044`~`049`):

- **Merge** joins datasets only when their feature schema, `fps` and `robot_type` are
  identical and their follower PD gain profile is the same. A differing
  `observation.state` shape means `use_velocity_and_torque` diverged and the merge is
  meaningless; a gain-tagless source is FAIL_BLOCKING, because gain drives the
  following-error distribution and an untagged source could silently mix distributions.
- **Split** partitions by ratio or by explicit episode index, on episode boundaries
  only — a frame never crosses a split.
- **Train/val** keeps the physical `split` distinct from the training `eval_split`,
  computes their composition, and blocks `eval_steps > 0` with `eval_split == 0.0`.

The merge and split *transformations* are the committed WP-3D-02 edit module's, imported
not re-implemented: merge is `MergeDatasets`' call to `lerobot merge_datasets` plus the
verified sidecar remap (`resolve_remap`/`apply_remap`), and split is the `SplitDataset`
copy-on-write edit (`commit_edit`). This package is the verification and policy around
them (`BATCH-2`, `06` §5.6).
"""

from __future__ import annotations

from backend.dataset.merge.gain import (
    GainProfile,
    GainProfileError,
    GainProfileMismatchError,
    GainTagMissingError,
    gain_profile_path,
    read_gain_profile,
    verify_uniform_gain,
    write_gain_profile,
)
from backend.dataset.merge.merge import (
    MergeOrigin,
    MergeOutputExistsError,
    MergeRefusedError,
    MergeRemapError,
    MergeResult,
    MergeSource,
    merge_datasets_verified,
    preflight_merge,
)
from backend.dataset.merge.schema import (
    DatasetSchema,
    MergeSchemaError,
    MergeSchemaReadError,
    verify_mergeable_schema,
)
from backend.dataset.merge.split import (
    SplitError,
    plan_ratio_split,
    split_by_index,
    split_by_ratio,
    validate_index_split,
)
from backend.dataset.merge.trainval import (
    EffectiveSplitRatios,
    EvalConfigError,
    compose_split_ratios,
    eval_split_of,
    validate_eval_config,
)

__all__ = [
    "DatasetSchema",
    "EffectiveSplitRatios",
    "EvalConfigError",
    "GainProfile",
    "GainProfileError",
    "GainProfileMismatchError",
    "GainTagMissingError",
    "MergeOrigin",
    "MergeOutputExistsError",
    "MergeRefusedError",
    "MergeRemapError",
    "MergeResult",
    "MergeSchemaError",
    "MergeSchemaReadError",
    "MergeSource",
    "SplitError",
    "compose_split_ratios",
    "eval_split_of",
    "gain_profile_path",
    "merge_datasets_verified",
    "plan_ratio_split",
    "preflight_merge",
    "read_gain_profile",
    "split_by_index",
    "split_by_ratio",
    "validate_eval_config",
    "validate_index_split",
    "verify_mergeable_schema",
    "verify_uniform_gain",
    "write_gain_profile",
]
