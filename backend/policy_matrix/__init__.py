"""WP-0C-08 — the three-axis policy compatibility matrix.

`10` FR-TRN-064/065 and `11` FR-INF-033/034 require that, before training or
deployment, an incompatible {dataset observation config, policy, deploy target}
combination is BLOCKED — not warned about. This package is that block, computed
across three axes and enforced as a hard stop:

- `caps` — the policy dimension ceilings, introspected off the installed configs
  (never a hardcoded 32), plus the async-chunking defaults (`16` D-11).
- `registry` — `contracts/policy_compat.yaml` loaded and cross-checked against
  introspection, `targets.guards`, and the fleet target list.
- `matrix` — the calculator: dataset config x policy ceiling x target capability,
  reusing WP-0C-07's constraints and WP-ENV-02's guards, with `usable_policies`
  auto-dropping the 32-capped policies when a 24-dim config becomes 48-dim.
- `enforce` — the hard block (`PolicyCompatBlockedError`) and the async fallback plan,
  which rejects an unset `actions_per_chunk` and defaults the threshold to the
  introspected 0.5.
- `provenance` — the `env_hash` / `normalization_hash` manifest the launch
  barriers check.

`contracts/policy_compat.yaml` is a work-package output artifact, deliberately
outside the 13 frozen CTR-* contracts.
"""

from __future__ import annotations

from backend.policy_matrix.caps import (
    POLICY_CONFIGS,
    PolicyCaps,
    actions_per_chunk_is_required,
    async_chunk_size_threshold_default,
    introspect_caps,
)
from backend.policy_matrix.enforce import (
    AsyncChunkingPlan,
    PolicyCompatBlockedError,
    build_async_chunking_plan,
    enforce,
    first_block,
)
from backend.policy_matrix.matrix import (
    Block,
    DatasetObsConfig,
    DeployRequest,
    MatrixCell,
    PolicyMatrix,
    build_matrix,
)
from backend.policy_matrix.provenance import build_provenance_manifest
from backend.policy_matrix.registry import (
    BlockedPath,
    BlockReason,
    PolicyCompatEntry,
    load_registry,
    verify_against_introspection,
    verify_env04_predicate,
)

__all__ = [
    "POLICY_CONFIGS",
    "AsyncChunkingPlan",
    "Block",
    "BlockReason",
    "BlockedPath",
    "DatasetObsConfig",
    "DeployRequest",
    "MatrixCell",
    "PolicyCaps",
    "PolicyCompatBlockedError",
    "PolicyCompatEntry",
    "PolicyMatrix",
    "actions_per_chunk_is_required",
    "async_chunk_size_threshold_default",
    "build_async_chunking_plan",
    "build_matrix",
    "build_provenance_manifest",
    "enforce",
    "first_block",
    "introspect_caps",
    "load_registry",
    "verify_against_introspection",
    "verify_env04_predicate",
]
