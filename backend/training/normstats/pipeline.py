"""End-to-end: fit train-only statistics, then embed them as a frozen contract.

This wires the band's parts in the one correct order — refuse to freeze a contract over
a dataset that failed observation-configuration preflight, fit normalization on the
TRAIN split via the committed `fit_dataset_stats` (which yields the train
`NormalizationStats` and keeps every other split as a `DiagnosticStats`), then build
the contract from that train statistic and never a diagnostic. A caller (WP-4A-05
lineage, WP-4B-02 the serving gate) gets one entry point that cannot take the leakage
path.

The preflight precondition is why this band consumes WP-4A-02: a `stats_hash` is only
meaningful over a valid observation configuration. If the `names` were torque-stripped
or rotated (the WP-4A-02 faults), the statistics are computed over misaligned channels
and the hash would freeze garbage into the checkpoint's lineage — so a `PreflightReport`
that is not PASS blocks the freeze here (`FR-TRN-024` fits a valid dataset, not any).

It is also the owned tree's one real `build_normalization_contract` call site, which
keeps `staticcheck` non-vacuous: the argument here is `fitted.normalization` (the train
statistic), so the scan passes on real code and only a diagnostic argument would fail.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from backend.dataset.stats import EpisodeData, FittedStats, fit_dataset_stats
from backend.training.normstats.contract import NormalizationContract, build_normalization_contract
from backend.training.preflight import PreflightReport, Verdict


class ContractPreflightError(RuntimeError):
    """Raised when a contract freeze is requested over a dataset that failed preflight.

    A normalization contract pins a checkpoint's model input; freezing one over a
    dataset whose observation configuration did not pass preflight (WP-4A-02) would
    hash statistics computed over misaligned channels. The freeze is refused rather
    than silently recording a hash of garbage.
    """


@dataclass(frozen=True)
class ContractedStatistics:
    """A dataset's fitted statistics and the normalization contract built from them.

    Attributes:
        fitted: Train normalization plus per-split diagnostics (the diagnostics are
            never a contract input — `FR-DAT-031`).
        contract: The frozen contract carrying the canonical train stats hash.
    """

    fitted: FittedStats
    contract: NormalizationContract


def fit_and_build_contract(
    preflight_report: PreflightReport,
    episodes_by_split: Mapping[str, Iterable[EpisodeData]],
    features: Mapping[str, object],
) -> ContractedStatistics:
    """Fit train-only statistics and embed them as a normalization contract.

    Refuses a dataset that failed preflight (WP-4A-02), then fits normalization ONLY
    from the train split (the committed `fit_dataset_stats` refuses any other) and
    builds the contract from that train statistic alone — so the leakage `FR-TRN-024`
    forbids is impossible by construction and the frozen hash covers a valid dataset.

    Args:
        preflight_report: The WP-4A-02 verdict; the contract is frozen only over a
            dataset whose observation configuration already passed.
        episodes_by_split: Split name to per-episode inputs; must contain the train
            split.
        features: The shared `features` description.

    Returns:
        (ContractedStatistics) The fitted statistics and the frozen contract.

    Raises:
        ContractPreflightError: When the preflight verdict is not PASS.
    """
    if preflight_report.verdict is not Verdict.PASS:
        raise ContractPreflightError(
            "cannot freeze a normalization contract over a dataset that failed preflight "
            f"(verdict {preflight_report.verdict}); resolve the observation-configuration "
            "findings first (WP-4A-02)"
        )
    fitted = fit_dataset_stats(episodes_by_split, features)
    contract = build_normalization_contract(fitted.normalization)
    return ContractedStatistics(fitted=fitted, contract=contract)
