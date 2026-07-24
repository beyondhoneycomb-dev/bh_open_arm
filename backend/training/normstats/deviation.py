"""Bind the contract's approximate quantiles to an exact-vs-approx deviation report.

`FR-DAT-029` records that a fitted table's quantiles are a histogram estimate
(`num_quantile_bins=5000`), never exact, and requires the exact values be computed
separately with the deviation reported — so the approximation error is MEASURED, not
assumed. The measurement itself is the committed `backend.dataset.stats.
quantile_deviation_report` (WP-3D-03); this band does not reimplement it. What it adds
is the tie to the contract: a report is meaningful only for a contract that declares
its quantiles approximate, and this asserts that link so a caller cannot pair an
exact-quantile contract with an approximation report.

`CG-4A-04e` is an EXISTENCE check, not a value gate: the deviation report must exist
for the contract, whatever its magnitude.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from backend.dataset.stats import QuantileDeviationReport, quantile_deviation_report
from backend.training.normstats.contract import NormalizationContract


def contract_quantile_deviation_report(
    contract: NormalizationContract,
    approx: Mapping[str, Mapping[str, np.ndarray]],
    values_by_feature: Mapping[str, np.ndarray],
) -> QuantileDeviationReport:
    """Report the exact-vs-approximate quantile deviation for an approximate contract.

    Delegates the measurement to the committed `quantile_deviation_report`; the only
    thing added here is the contract precondition, since a deviation report has no
    meaning for a contract whose quantiles are not approximate.

    Args:
        contract: The contract whose quantiles the report characterizes; must declare
            `quantile_approx`.
        approx: The fitted per-feature table carrying the histogram-approximate
            quantiles (`q01`..`q99`).
        values_by_feature: The `(frames, channels)` values the exact quantiles are
            computed over.

    Returns:
        (QuantileDeviationReport) The per-channel, per-level deviations and the maximum.

    Raises:
        ValueError: When the contract does not declare its quantiles approximate.
    """
    if not contract.quantile_approx:
        raise ValueError(
            "quantile deviation report requires a contract that declares approximate "
            "quantiles (FR-DAT-029); this contract sets quantile_approx=False"
        )
    return quantile_deviation_report(approx, values_by_feature)
