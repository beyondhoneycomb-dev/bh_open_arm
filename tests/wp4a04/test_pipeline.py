"""The end-to-end pipeline fits train-only and embeds the contract (`02c` §1.4).

`fit_and_build_contract` is the one entry point that cannot take the leakage path: it
refuses a dataset that failed preflight (WP-4A-02), fits normalization on the TRAIN
split via the committed fit (which yields diagnostics for every other split) and builds
the contract from the train statistic alone. This also exercises the real
`build_normalization_contract` call the static leakage scan relies on for non-vacuity.
"""

from __future__ import annotations

import pytest

import backend.dataset.stats as stats
from backend.training.normstats import (
    ContractPreflightError,
    build_normalization_contract,
    fit_and_build_contract,
)
from backend.training.preflight import PreflightCode, PreflightFinding, PreflightReport
from tests.wp4a04 import support


def _passing_preflight() -> PreflightReport:
    """A PASS preflight report (empty findings)."""
    return PreflightReport.from_findings(())


def _blocking_preflight() -> PreflightReport:
    """A BLOCK preflight report carrying one located fault."""
    return PreflightReport.from_findings(
        (
            PreflightFinding(
                code=PreflightCode.OBSERVATION_STATE_ORDER,
                channel_name="left_joint_1.torque",
                component=None,
                joint="left_joint_1",
                detail="names order rotated",
            ),
        )
    )


def test_pipeline_builds_the_contract_from_the_train_statistic() -> None:
    """The pipeline's contract hash equals the hash of the train normalization alone."""
    result = fit_and_build_contract(
        _passing_preflight(), support.split_episodes(), support.features()
    )

    assert result.contract.stats_hash == stats.stats_content_hash(result.fitted.normalization)
    assert result.contract.fit_split == "train"


def test_pipeline_keeps_non_train_splits_as_diagnostics_only() -> None:
    """val/test yield diagnostics that never enter the contract (FR-DAT-031)."""
    result = fit_and_build_contract(
        _passing_preflight(), support.split_episodes(), support.features()
    )

    assert set(result.fitted.diagnostics) == {"val", "test"}
    # The contract equals one built from the train statistic — diagnostics contribute nothing.
    assert result.contract == build_normalization_contract(result.fitted.normalization)


def test_pipeline_refuses_to_freeze_over_a_failed_preflight() -> None:
    """A non-PASS preflight blocks the freeze — no hash of a misaligned dataset."""
    with pytest.raises(ContractPreflightError):
        fit_and_build_contract(_blocking_preflight(), support.split_episodes(), support.features())
