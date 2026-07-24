"""The report's own invariants: the required set, and no-crash robustness.

The verifier promises a fixed, complete check set and that no dataset — however
corrupt — makes it raise instead of returning INVALID. Both are pinned here.
"""

from __future__ import annotations

from backend.dataset.integrity import REQUIRED_CHECKS, verify_dataset
from backend.dataset.integrity.checks import ALL_CHECKS
from tests.wp3d05.materialize import MaterializedDataset


def test_all_checks_produce_exactly_the_required_names(materialized: MaterializedDataset) -> None:
    report = verify_dataset(materialized.root)
    produced = tuple(result.name for result in report.results)
    assert produced == REQUIRED_CHECKS
    assert len(ALL_CHECKS) == len(REQUIRED_CHECKS)


def test_empty_directory_is_invalid_not_a_crash(tmp_path) -> None:
    report = verify_dataset(tmp_path)
    assert report.verdict == "INVALID"
    # Every required check still produced a result rather than raising.
    assert report.checks_ran == frozenset(REQUIRED_CHECKS)


def test_footer_check_runs_even_when_layout_is_unreadable(tmp_path) -> None:
    """A dataset with no info.json still gets its parquet footers judged.

    The footer check globs the raw tree, so it does not depend on the layout the
    other checks need; a missing info.json fails those, not this one.
    """
    (tmp_path / "data" / "chunk-000").mkdir(parents=True)
    (tmp_path / "data" / "chunk-000" / "file-000.parquet").write_bytes(b"not a parquet")
    report = verify_dataset(tmp_path)
    footer = report.result("parquet_footer")
    assert footer is not None and not footer.passed
