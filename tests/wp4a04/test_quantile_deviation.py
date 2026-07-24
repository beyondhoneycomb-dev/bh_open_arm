"""CG-4A-04e — the exact-vs-approx quantile deviation report exists (`02c` §1.4).

`FR-DAT-029`: a fitted table's quantiles are a histogram estimate (5000 bins), so the
contract records `quantile_approx=True` and the exact-vs-approximate deviation is
reported. This is an EXISTENCE check, not a value gate — the report must exist for the
contract, whatever its magnitude. The measurement is the committed reporter; this band
ties it to the contract and refuses to characterize a contract that is not approximate.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.training.normstats import (
    build_normalization_contract,
    contract_quantile_deviation_report,
)
from tests.wp4a04 import support


def test_deviation_report_exists_for_an_approximate_contract() -> None:
    """An approximate contract yields a non-empty per-channel deviation report."""
    episodes = [support.episode(index) for index in range(3)]
    fitted = support.fit()
    contract = build_normalization_contract(fitted)

    report = contract_quantile_deviation_report(
        contract, fitted.per_feature, support.concat_values(episodes)
    )

    # Existence, not value: the report is present and covers channels at every level.
    assert report.deviations
    assert report.max_abs_deviation >= 0.0


def test_report_is_refused_for_a_non_approximate_contract() -> None:
    """A contract that declares exact quantiles has no meaningful deviation report."""
    episodes = [support.episode(index) for index in range(3)]
    fitted = support.fit()
    contract = dataclasses.replace(build_normalization_contract(fitted), quantile_approx=False)

    with pytest.raises(ValueError, match="approximate"):
        contract_quantile_deviation_report(
            contract, fitted.per_feature, support.concat_values(episodes)
        )
