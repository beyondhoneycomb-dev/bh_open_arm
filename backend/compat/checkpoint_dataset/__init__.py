"""WP-4B-02 — the checkpoint<->dataset compatibility gate (`02c` §2.2).

The COMPARER half of the stats-hash contract, kept in its own package: WP-4A-04 makes
the hash and WP-3D-03 owns the canonicalization, and this band imports `verify_stats_
hash` to COMPARE rather than re-canonicalizing (`gate`). It refuses a checkpoint fed a
dataset whose `observation.state`/`action` do not match by `names` (`FR-TRN-062`,
`gate`), escalates a serving stats-hash mismatch to a deployment BLOCK over the
`FR-DAT-032` warning (`FR-TRN-025`, `OA-DAT-002`, `verdict`), and propagates that block
to descendant checkpoints when a dataset's statistics are recomputed (`stale`).

It owns the gate, not a copy of its inputs: the WP-4A-05 lineage, the WP-4A-04
normalization contract, the WP-4A-02 observation config and the WP-4B-01 matrix are
consumed by import, never restated.
"""

from __future__ import annotations

from backend.compat.checkpoint_dataset.gate import (
    RULE_LINEAGE_CONSISTENCY,
    RULE_SERVING_STATS,
    RULE_SHAPE,
    STATS_BLOCK_CODE,
    assert_deployable,
    check_compatibility,
)
from backend.compat.checkpoint_dataset.inputs import CheckpointAttachment, DatasetTarget
from backend.compat.checkpoint_dataset.stale import (
    is_deployment_stale,
    stale_deployments,
)
from backend.compat.checkpoint_dataset.verdict import (
    CheckpointDatasetMismatchError,
    CheckpointDatasetVerdict,
    DeploymentIntent,
    IncompatibilityCode,
    IncompatibilityReason,
)

__all__ = [
    "RULE_LINEAGE_CONSISTENCY",
    "RULE_SERVING_STATS",
    "RULE_SHAPE",
    "STATS_BLOCK_CODE",
    "CheckpointAttachment",
    "CheckpointDatasetMismatchError",
    "CheckpointDatasetVerdict",
    "DatasetTarget",
    "DeploymentIntent",
    "IncompatibilityCode",
    "IncompatibilityReason",
    "assert_deployable",
    "check_compatibility",
    "is_deployment_stale",
    "stale_deployments",
]
