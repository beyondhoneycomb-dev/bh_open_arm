"""A skipped check fails the build as loudly as a failed one (`02b` §8.2 WP-3D-05).

The negative branch is a missing check => FAIL_BLOCKING: a verifier that ran fewer
than the required checks must not be able to certify a dataset READY by omission.
The report tests the required-check set, not just the presence of failures, so a
subset run is INVALID even when every check that did run passed.
"""

from __future__ import annotations

from backend.dataset.integrity import (
    CHECK_PARQUET_FOOTER,
    REQUIRED_CHECKS,
    verify_dataset,
)
from backend.dataset.integrity.checks import check_parquet_footer
from tests.wp3d05.materialize import MaterializedDataset


def test_subset_run_is_invalid_despite_all_passing(materialized: MaterializedDataset) -> None:
    report = verify_dataset(materialized.root, checks=(check_parquet_footer,))

    assert report.failures == ()  # the one check that ran passed
    assert report.ready is False  # but the dataset is still not READY
    assert set(report.missing_checks) == set(REQUIRED_CHECKS) - {CHECK_PARQUET_FOOTER}


def test_missing_checks_are_reported(materialized: MaterializedDataset) -> None:
    report = verify_dataset(materialized.root, checks=(check_parquet_footer,))
    assert len(report.missing_checks) == len(REQUIRED_CHECKS) - 1
