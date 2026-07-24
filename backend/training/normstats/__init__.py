"""WP-4A-04 — the normalization-stats contract and its serving hash gate (`02c` §1.4).

`FR-TRN-024` makes the normalization statistics part of the model input contract: they
are enclosed immutably in the checkpoint's lineage, keyed by a content hash, and the
normalization direction is canon — fit on the TRAIN split only, apply the SAME
statistics to val/test and real inference. A per-split re-fit is validation leakage and
forbidden (`FR-DAT-031`).

This band builds ON TOP of the committed WP-3D-03 statistics module; it does not fork
it. The stats content hash is the single canonicalization rule (`02c` §1.4 SHAPE-CF),
so `stats_hash` is the committed `backend.dataset.stats.stats_content_hash` — imported,
never redefined. On that one hash this band adds:

- `contract` — the frozen `NormalizationContract` (`stats_hash`, `fit_split=train`,
  `applied_to`, `quantile_approx`, `quantile_bins=5000`), built only from the train
  `NormalizationStats`, and a staleness check: a one-bit change to the statistics
  yields a new hash, so every checkpoint on the old hash is stale (`CG-4A-04b`);
- `serving` — the deployment BLOCK gate (`FR-TRN-025`): a serving hash that differs
  from the training contract raises `OA-DAT-002` and no clearance is minted. This is
  the BLOCK half of the `OA-DAT-002` condition; the committed
  `warn_on_stats_hash_mismatch` is the WARN half (`FR-DAT-032`) — the plan escalates
  to a block because differing statistics mean differing denormalization, i.e. wrong
  physical units (`CG-4A-04d`);
- `deviation` — the exact-vs-approx quantile deviation report tied to the contract's
  approximate quantiles, delegating the measurement to the committed reporter
  (`CG-4A-04e`, an existence check);
- `staticcheck` — the static proof that no diagnostic (split-local) statistic reaches
  the contract builder, reusing the committed diagnostic definitions (`CG-4A-04c`);
- `pipeline` — the one entry point that fits train-only and embeds the contract.
"""

from __future__ import annotations

from backend.training.normstats.constants import (
    APPLIED_TO,
    FIT_SPLIT,
    QUANTILE_APPROX,
    QUANTILE_BINS,
    REAL_INFERENCE,
)
from backend.training.normstats.contract import (
    NormalizationContract,
    build_normalization_contract,
    contract_is_stale,
)
from backend.training.normstats.deviation import contract_quantile_deviation_report
from backend.training.normstats.pipeline import (
    ContractedStatistics,
    ContractPreflightError,
    fit_and_build_contract,
)
from backend.training.normstats.serving import (
    ServingDeploymentClearance,
    ServingHashMismatchError,
    clear_for_serving,
)
from backend.training.normstats.staticcheck import scan_source, scan_tree

__all__ = [
    "APPLIED_TO",
    "FIT_SPLIT",
    "QUANTILE_APPROX",
    "QUANTILE_BINS",
    "REAL_INFERENCE",
    "ContractPreflightError",
    "ContractedStatistics",
    "NormalizationContract",
    "ServingDeploymentClearance",
    "ServingHashMismatchError",
    "build_normalization_contract",
    "clear_for_serving",
    "contract_is_stale",
    "contract_quantile_deviation_report",
    "fit_and_build_contract",
    "scan_source",
    "scan_tree",
]
