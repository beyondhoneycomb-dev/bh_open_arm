"""A whole dataset verifies READY, and every required check ran and passed.

READY is the precondition for a dataset to be a training input; this pins that a
well-formed dataset earns it and that no required check was silently skipped.
"""

from __future__ import annotations

from backend.dataset.integrity import (
    REQUIRED_CHECKS,
    VERDICT_READY,
    CheckStatus,
    IntegrityReport,
    ensure_training_ready,
    is_ready,
    verify_dataset,
)
from tests.wp3d05.materialize import MaterializedDataset


def test_valid_dataset_is_ready(materialized: MaterializedDataset) -> None:
    report = verify_dataset(materialized.root)
    assert report.verdict == VERDICT_READY
    assert report.ready is True
    assert report.failures == ()


def test_every_required_check_ran_and_passed(materialized: MaterializedDataset) -> None:
    report = verify_dataset(materialized.root)
    assert report.checks_ran == frozenset(REQUIRED_CHECKS)
    assert report.missing_checks == ()
    assert all(result.status is CheckStatus.PASS for result in report.results)


def test_is_ready_shortcut(materialized: MaterializedDataset) -> None:
    assert is_ready(materialized.root) is True


def test_ensure_training_ready_returns_report(materialized: MaterializedDataset) -> None:
    report = ensure_training_ready(materialized.root)
    assert isinstance(report, IntegrityReport)
    assert report.ready is True
