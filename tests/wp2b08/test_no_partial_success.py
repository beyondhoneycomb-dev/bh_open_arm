"""WP-2B-08 negative branch: path B may never be recorded as a partial success.

02b §2.1/§2.3: recording path B as a "partial success" is itself the FAIL_BLOCKING defect — the
twin's gravity comes alive, but detection cannot be turned on, so PG-FRIC-001 is still a failure.
These tests pin that the outcome is FAIL_BLOCKING with no way to set it otherwise, and that the
reporting boundary refuses any PASS / DEGRADED / "partial success" value.
"""

from __future__ import annotations

import pytest

from backend.pathb import PG_FRIC_OUTCOME, PathBBootstrap, PathBError


def test_outcome_is_fail_blocking(bootstrap: PathBBootstrap) -> None:
    """Path B's PG-FRIC-001 outcome is FAIL_BLOCKING."""
    assert bootstrap.pg_fric_outcome == "FAIL_BLOCKING"
    assert bootstrap.pg_fric_outcome == PG_FRIC_OUTCOME


def test_outcome_has_no_setter(bootstrap: PathBBootstrap) -> None:
    """The outcome is read-only: no attribute lets a caller record a pass."""
    with pytest.raises(AttributeError):
        bootstrap.pg_fric_outcome = "PASS"  # type: ignore[misc]


def test_record_outcome_accepts_only_fail_blocking(bootstrap: PathBBootstrap) -> None:
    """Recording FAIL_BLOCKING succeeds and returns it."""
    assert bootstrap.record_outcome("FAIL_BLOCKING") == "FAIL_BLOCKING"


def test_record_outcome_refuses_partial_success(bootstrap: PathBBootstrap) -> None:
    """Any PASS / DEGRADED / partial-success record is refused at the reporting boundary."""
    for outcome in ("PASS", "DEGRADED_ACCEPTED", "partial success", "RETRY_WITH_VARIANT", ""):
        with pytest.raises(PathBError):
            bootstrap.record_outcome(outcome)
