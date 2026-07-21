"""The check report reaches disk, and the dashboard reads the shape it finds.

The report is the only channel by which a rule's execution becomes visible to
anything outside the process that ran it. Two ways that channel breaks silently,
both of which leave every rule reading as unproven forever while the checks
themselves are perfectly healthy:

- nothing writes the file the reader opens, so the reader always takes its
  absent branch;
- both sides exist but disagree on the shape, so the reader parses a real report
  into nothing.

These tests pin the path and the shape from both ends, because either end can be
edited alone and no other test in the suite compares them.

Nothing here asserts that a particular rule currently fails. Which rules fail is
the band's work in progress, and a test that hardcodes today's failures starts
failing the moment someone fixes one — punishing exactly the work the gate
exists to encourage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dashboard import render
from registry.check import EXIT_OK, REPORT_RELPATH, main, write_report

REPO_ROOT = Path(__file__).resolve().parents[2]

# Two rules run together, chosen only to keep these tests off the full range.
# The assertions hold whether either one passes or fails.
SAMPLE_RULES = ("CI-01", "CI-07")


def _run(tmp_path: Path, argv: list[str]) -> tuple[int, dict[str, Any]]:
    """Run the checker with the report redirected out of the working tree.

    Args:
        tmp_path: Destination directory for the report.
        argv: Extra arguments, appended to root and report redirection.

    Returns:
        (tuple[int, dict[str, Any]]) Exit status and the parsed report.
    """
    report_path = tmp_path / "check-report.json"
    status = main(["--root", str(REPO_ROOT), "--report", str(report_path), *argv])
    assert report_path.exists(), f"run left no report at {report_path}"
    parsed: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    return status, parsed


def _status_for(rule_id: str, statuses: list[render.RuleStatus]) -> render.RuleStatus:
    """Pick one rule out of a rendered status list.

    Args:
        rule_id: Rule to find.
        statuses: Rendered statuses.

    Returns:
        (render.RuleStatus) The matching status.
    """
    return next(status for status in statuses if status.rule_id == rule_id)


def test_report_lands_where_the_dashboard_looks() -> None:
    """The writer's default path is the reader's path.

    Pinned from both ends. A report written somewhere the dashboard does not
    open is worth exactly as much as no report at all.
    """
    assert REPO_ROOT / REPORT_RELPATH == render.REPORT_PATH


@pytest.mark.parametrize("argv", [[], ["--rule", SAMPLE_RULES[0]], ["--all"]])
def test_report_is_written_whatever_the_outcome(tmp_path: Path, argv: list[str]) -> None:
    """Every run leaves a record, and the exit status still follows the verdict.

    `_run` asserts the file exists, so a pass-only write fails here on whichever
    parameter is currently red. The status assertion is the exit-code contract:
    writing a file must not change what the process returns.
    """
    status, report = _run(tmp_path, argv)
    assert (status == EXIT_OK) is report["green"]


def test_write_report_records_a_failed_run(tmp_path: Path) -> None:
    """A failed verdict survives the round trip to disk.

    Synthetic rather than corpus-driven: the point is that failure is written at
    all, and that must stay proven even on the day every real rule is green.
    """
    report_path = tmp_path / "nested" / "check-report.json"
    failed = {"green": False, "judged_findings_total": 4, "rules": []}

    write_report(failed, report_path)

    assert json.loads(report_path.read_text(encoding="utf-8")) == failed


def test_dashboard_reads_the_shape_check_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule the report says ran is never rendered as absent.

    This is the shape contract, exercised against a genuine report rather than a
    handwritten one. It fails if either side renames a key — the failure that
    leaves the page reporting "unproven" over a valid report sitting right there.
    """
    report_path = tmp_path / "check-report.json"
    main(
        [
            "--root",
            str(REPO_ROOT),
            "--report",
            str(report_path),
            *[arg for rule in SAMPLE_RULES for arg in ("--rule", rule)],
        ]
    )
    monkeypatch.setattr(render, "REPORT_PATH", report_path)

    statuses = render._load_rule_statuses()

    for rule_id in SAMPLE_RULES:
        assert _status_for(rule_id, statuses).state != render.STATE_ABSENT


def _write(report_path: Path, entry: dict[str, Any]) -> None:
    """Write a one-rule report.

    Args:
        report_path: Destination file.
        entry: The single rule entry to record.
    """
    report_path.write_text(json.dumps({"rules": [entry]}), encoding="utf-8")


def test_findings_become_the_failing_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A rule with findings renders as failing, carrying the real count."""
    finding_count = 3
    report_path = tmp_path / "report.json"
    _write(
        report_path,
        {
            "rule_id": SAMPLE_RULES[1],
            "sites": 9,
            "vacuous": False,
            "findings": [{"reason": "x"}] * finding_count,
            "notes": [],
        },
    )
    monkeypatch.setattr(render, "REPORT_PATH", report_path)

    status = _status_for(SAMPLE_RULES[1], render._load_rule_statuses())

    assert status.state == render.STATE_FAIL
    assert str(finding_count) in status.detail


def test_a_rule_that_judged_nothing_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vacuous rule is green, and its label admits it examined nothing.

    Green because it judged nothing is not the same claim as green because it
    judged and found nothing. The mark cannot draw the difference, so the label
    has to state it — a rule that is green while looking at zero sites is the
    outcome `02a` §−2.3 calls worse than having no rule at all.
    """
    report_path = tmp_path / "report.json"
    _write(
        report_path,
        {"rule_id": SAMPLE_RULES[0], "sites": 0, "vacuous": True, "findings": [], "notes": []},
    )
    monkeypatch.setattr(render, "REPORT_PATH", report_path)

    status = _status_for(SAMPLE_RULES[0], render._load_rule_statuses())

    assert status.state == render.STATE_PASS
    assert "0건" in status.detail


def test_missing_report_leaves_every_rule_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No report means unproven, not green.

    The absent state must stay reachable. It is the whole reason the page has
    three states rather than two, and a wiring change that renders "no evidence"
    as "pass" is the failure the band gate exists to prevent.
    """
    monkeypatch.setattr(render, "REPORT_PATH", tmp_path / "does-not-exist.json")

    statuses = render._load_rule_statuses()

    assert statuses, "no rules were enumerated at all"
    assert all(status.state == render.STATE_ABSENT for status in statuses)

    document = {"entries": [{"wp": f"WP-{index}"} for index in range(render.ISSUED_PACKAGE_COUNT)]}
    state, _, _ = render._verdict(statuses, document)
    assert state == render.STATE_ABSENT
