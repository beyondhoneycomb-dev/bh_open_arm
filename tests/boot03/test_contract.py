"""The roster, the report shape, and the two ranges that must stay different.

`02a` §−2.3 acceptance ①, ⑩ and ⑫. The roster is a contract in both directions:
`06` §5 owns the rules, this package owns the executables, and adding a check that
`06` §5 lacks is as much a violation as omitting one it has.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from registry.checks import BUILD_RANGE, JUDGE_EXCLUDED, JUDGE_RANGE, RULE_IDS
from registry.checks.corpus import Corpus
from registry.checks.model import (
    MIN_POPULATED_FIELDS,
    CheckerContractError,
    Finding,
    fail,
)
from registry.ingest.markdown import all_tables, plain_text

REPO_ROOT = Path(__file__).resolve().parents[2]

RULE_CANON = REPO_ROOT / "docs" / "plan" / "06-추적성-레지스트리.md"

# `06` §5 states the report shape; a record below the floor means the checker failed.
CANONICAL_FIELDS = ("rule_id", "severity", "req_or_wp", "path", "reason")

# The row id 06 §5 uses for CI-11b's self-application obligation.
SELF_APPLICATION_ROW = "CI-11b-자기적용"

RULE_ID_CELL = re.compile(r"^CI-\d{2}[a-z]?$")


def _rules_declared_by_canon() -> set[str]:
    """Read the rule ids `06` §5 declares.

    Matching is on a whole-cell rule id rather than a `CI-` prefix, because other
    tables in the document open a row with prose that begins with a range such as
    "CI-01~CI-18 …". That is a sentence about the rules, not a rule.

    Returns:
        (set[str]) Rule ids named in the first column of the rule tables.
    """
    declared: set[str] = set()
    for table in all_tables(RULE_CANON):
        for row in table.rows:
            if not row:
                continue
            cell = plain_text(row[0]).strip()
            if RULE_ID_CELL.match(cell) or cell == SELF_APPLICATION_ROW:
                declared.add(cell)
    return declared


def test_every_canon_rule_has_an_executable() -> None:
    """No rule in `06` §5 is missing an executable."""
    declared = _rules_declared_by_canon()
    # The self-application row is an obligation on CI-11b, not a separate rule with
    # its own executable; tests/boot03/test_self_application.py discharges it.
    declared.discard(SELF_APPLICATION_ROW)
    missing = sorted(declared - set(RULE_IDS))
    assert not missing, f"rules declared in 06 §5 with no executable: {missing}"


def test_no_executable_invents_a_rule() -> None:
    """No executable exists for a rule `06` §5 does not declare."""
    declared = _rules_declared_by_canon()
    # CI-16 is declared in `06` §5.6 as its own subsection rather than as a row of
    # the §5 table, so it is canon without appearing in the table scan.
    declared.add("CI-16")
    invented = sorted(set(RULE_IDS) - declared)
    assert not invented, f"executables for rules 06 §5 does not declare: {invented}"


def test_build_range_covers_ci_01_through_ci_18() -> None:
    """The build range runs to CI-18."""
    assert "CI-18" in RULE_IDS
    assert len(BUILD_RANGE) == len(set(RULE_IDS)) == len(RULE_IDS)


def test_judge_range_stops_at_ci_17() -> None:
    """The judge range excludes CI-18, and the difference is deliberate.

    `06` §5 and `02a` §−2.3 both warn against making the two numbers match: CI-18's
    predicate cites the band acceptance gate, so judging by it would make the gate
    reference itself.
    """
    judged = {module.RULE_ID for module in JUDGE_RANGE}
    assert "CI-18" not in judged
    assert set(RULE_IDS) - judged == set(JUDGE_EXCLUDED)
    assert len(JUDGE_RANGE) == len(BUILD_RANGE) - 1


@pytest.mark.parametrize("module", BUILD_RANGE, ids=[m.RULE_ID for m in BUILD_RANGE])
def test_executable_declares_its_identity(module) -> None:
    """Each executable names the rule it implements and what it is for."""
    assert module.RULE_ID.startswith("CI-")
    assert module.TITLE and module.__doc__


def test_report_record_carries_the_canonical_fields() -> None:
    """A finding renders the five canonical fields of `06` §5."""
    record = fail("CI-05e", "WP-3A-00/CG-3A-00a", "registry/traceability.yaml", "binary only")
    rendered = record.as_dict()
    for field in CANONICAL_FIELDS:
        assert rendered[field], f"canonical field {field} is empty"


def test_report_record_below_the_field_floor_is_a_checker_failure() -> None:
    """A record populating fewer than four canonical fields raises, not reports."""
    with pytest.raises(CheckerContractError):
        Finding(rule_id="CI-01", severity="FAIL", req_or_wp="", path="", reason="")


def test_report_record_rejects_a_warning_level() -> None:
    """There is no severity but FAIL; a warning level cannot be constructed."""
    with pytest.raises(CheckerContractError):
        Finding(
            rule_id="CI-01",
            severity="WARN",
            req_or_wp="FR-CAM-001",
            path="registry/traceability.yaml",
            reason="something",
        )


def test_minimum_field_floor_matches_the_canon() -> None:
    """The floor is four of five, as `06` §5 states."""
    assert MIN_POPULATED_FIELDS == 4
    assert len(CANONICAL_FIELDS) == 5


def test_entry_point_exits_non_zero_on_violations() -> None:
    """The single entry point signals failure through its exit status."""
    result = subprocess.run(
        ["python", "-m", "registry.check", "--rule", "CI-04"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "a corpus with known violations exited zero"
    assert "CI-04" in result.stdout


def test_ci13_detects_a_gate_change_without_a_stale_set_diff(monkeypatch) -> None:
    """CI-13 is commit-scoped, so its fixtures are changed-path sets."""
    from registry.checks import ci_13

    corpus = Corpus(REPO_ROOT)

    monkeypatch.setattr(
        ci_13, "changed_paths", lambda c, r: ("registry/state/gates/PG-RT-001a.json",)
    )
    violating = ci_13.run(corpus, "fixture")
    assert violating.findings, "CI-13 missed a gate-state change with no stale set diff"

    monkeypatch.setattr(
        ci_13,
        "changed_paths",
        lambda c, r: ("registry/state/gates/PG-RT-001a.json", "registry/state/stale_set.json"),
    )
    passing = ci_13.run(corpus, "fixture")
    assert not passing.findings, "CI-13 over-blocks when the stale set is updated"
