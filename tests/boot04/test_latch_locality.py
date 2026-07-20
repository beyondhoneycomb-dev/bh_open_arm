"""Acceptance ⑤ — zero latch call sites outside the package that owns the latch path.

The fixture corpus is excluded by explicit path, never by a name convention inside the checker.
If the checker skipped anything called "fixtures" on its own initiative, hiding a real local
latch would be a matter of naming a directory.
"""

from __future__ import annotations

from pathlib import Path

from ops.cancel.staticcheck import OWNER_PACKAGE, find_external_latch_calls

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "boot04" / "fixtures"
WRONG_ORDER_FIXTURE = "wrong_order_cancel.py"
EVASIVE_FIXTURE = "evasive_latch.py"
CORRECT_FIXTURE = "correct_cancel_usage.py"


def test_repository_has_zero_external_latch_call_sites() -> None:
    """Acceptance ⑤ — the production tree applies the latch only from `ops/cancel/`."""
    violations = find_external_latch_calls(REPO_ROOT, exclude=[FIXTURE_DIR])
    assert violations == [], "\n".join(str(item) for item in violations)


def test_violation_fixture_local_latch_is_detected() -> None:
    """A checker that has never rejected anything is not known to be checking anything."""
    violations = find_external_latch_calls(FIXTURE_DIR)
    offenders = {item.path.name for item in violations}
    assert WRONG_ORDER_FIXTURE in offenders
    assert len(violations) >= 3


def test_violation_fixture_getattr_evasion_is_detected() -> None:
    """Reaching the latch through `getattr` is still applying the latch."""
    violations = find_external_latch_calls(FIXTURE_DIR)
    offenders = {item.path.name for item in violations}
    assert EVASIVE_FIXTURE in offenders


def test_pass_fixture_routing_through_the_owner_is_not_flagged() -> None:
    """Over-blocking check: triggering a latch via `cancel_stage` is legitimate."""
    violations = find_external_latch_calls(FIXTURE_DIR)
    offenders = {item.path.name for item in violations}
    assert CORRECT_FIXTURE not in offenders


def test_owning_package_is_not_flagged_against_itself() -> None:
    """The latch path lives in `ops/cancel/`; its own call sites are the point of the package."""
    owner = REPO_ROOT / OWNER_PACKAGE
    assert owner.is_dir()
    assert find_external_latch_calls(REPO_ROOT / "ops") == []


def test_violations_report_a_locatable_position() -> None:
    """A hit has to say where it is, or it cannot be acted on."""
    violations = find_external_latch_calls(FIXTURE_DIR)
    assert violations
    for violation in violations:
        assert violation.line > 0
        assert violation.path.exists()
        assert violation.symbol == "latch_to_hold"
