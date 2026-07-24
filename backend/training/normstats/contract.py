"""The frozen normalization contract embedded in a checkpoint's lineage (`02c` §1.4).

`FR-TRN-024` requires the normalization statistics be enclosed IMMUTABLY in the same
lineage record as the checkpoint, keyed by a hash of `stats.json`, and fixes the
normalization DIRECTION as canon: fit on the train split only, then apply the SAME
statistics to val/test and real inference. This module makes that a frozen object,
the `NormalizationContract`, which is the model-input contract a checkpoint's
`input_features` are pinned to.

Single source of truth for the hash: the `stats_hash` is computed by the committed
`backend.dataset.stats.stats_content_hash` (WP-3D-03 ④) — this band does NOT define
a second canonicalization. The stats hash is one of the `§0.4` stale axes, and two
canonicalization rules would split stale propagation; there is exactly one rule and
it lives upstream (`02c` §1.4 SHAPE-CF: single owner, no competing definition).

Train-split-only fit is enforced by TYPE here: `build_normalization_contract` accepts
only a `NormalizationStats`, the type the committed fit yields solely for the train
split (a non-train fit raises `LeakageError` and a diagnostic split yields the
distinct `DiagnosticStats`, which this signature refuses). `staticcheck` closes the
`Any`-bypass by forbidding a diagnostic value from ever reaching this builder.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.dataset.stats import NormalizationStats, stats_content_hash, verify_stats_hash
from backend.dataset.stats.hashing import StatsInput
from backend.training.normstats.constants import (
    APPLIED_TO,
    FIT_SPLIT,
    QUANTILE_APPROX,
    QUANTILE_BINS,
)


@dataclass(frozen=True)
class NormalizationContract:
    """The immutable normalization contract a checkpoint is trained and served under.

    Frozen because it is embedded in the lineage record and the checkpoint and must
    never be edited after the fact (`FR-TRN-024`: immutable enclosure). Two checkpoints
    with the same `stats_hash` normalize identically; a different `stats_hash` is a
    different contract, hence a different — and stale — model input (`CG-4A-04b`).

    Attributes:
        stats_hash: The committed `stats_content_hash` of the train normalization
            statistics — the single canonical digest, not a second rule.
        fit_split: The split the statistics were fit on; always `train` (`FR-TRN-024`).
        applied_to: Every context the one train statistic is applied to — the three
            splits plus real inference. val/test/real never re-fit (`FR-DAT-031`).
        quantile_approx: Always true: the quantiles are histogram estimates, not
            exact (`FR-DAT-029`).
        quantile_bins: The histogram resolution the quantiles were estimated at
            (`num_quantile_bins=5000`).
    """

    stats_hash: str
    fit_split: str = FIT_SPLIT
    applied_to: tuple[str, ...] = APPLIED_TO
    quantile_approx: bool = QUANTILE_APPROX
    quantile_bins: int = QUANTILE_BINS


def build_normalization_contract(stats: NormalizationStats) -> NormalizationContract:
    """Build the frozen contract from the TRAIN normalization statistics.

    Accepts only a `NormalizationStats` — the type the committed fit produces for the
    train split alone. A `DiagnosticStats` (a val/test split-local statistic) is a
    different type this signature rejects, so a split-local statistic cannot become a
    normalization contract by construction; `staticcheck` additionally proves no
    `Any`-typed diagnostic value reaches this builder (`CG-4A-04c`).

    The hash is the committed `stats_content_hash`; this function embeds it, it does
    not recompute a canonicalization of its own (`02c` §1.4 SHAPE-CF).

    Args:
        stats: The train-only normalization statistics.

    Returns:
        (NormalizationContract) The frozen contract carrying the canonical stats hash.
    """
    return NormalizationContract(stats_hash=stats_content_hash(stats))


def contract_is_stale(contract: NormalizationContract, current_stats: StatsInput) -> bool:
    """Report whether statistics have drifted from the contract's recorded hash.

    A one-bit change in the statistics yields a different `stats_content_hash`, so
    every checkpoint whose contract carries the OLD hash is stale against the new
    statistics — the `§0.4` stats axis (`CG-4A-04b`). Reuses the committed
    `verify_stats_hash` so the comparison uses the single canonical rule.

    Args:
        contract: The contract embedded in the checkpoint/lineage.
        current_stats: The statistics as they stand now (a fitted object or a raw
            table read back from disk).

    Returns:
        (bool) True when `current_stats` no longer hashes to `contract.stats_hash`.
    """
    return not verify_stats_hash(contract.stats_hash, current_stats)
