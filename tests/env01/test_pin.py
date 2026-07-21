"""WP-ENV-01 acceptance ① — the pin records the intended 0.6.1-vs-0.6.0 mismatch."""

from __future__ import annotations

from deps.pin import load_pin, validate_pin


def test_committed_pin_is_valid_and_records_the_mismatch() -> None:
    report = validate_pin(load_pin())
    assert report.ok, report.problems
    assert report.resolved_version == "0.6.0"
    assert report.self_claimed_version == "0.6.1"


def test_agreeing_versions_are_rejected() -> None:
    document = load_pin()
    document["self_claimed_version"] = "0.6.0"
    report = validate_pin(document)
    assert not report.ok
    assert any("mismatch is not recorded" in problem for problem in report.problems)


def test_mismatch_must_be_declared_intended() -> None:
    document = load_pin()
    document["version_mismatch_intended"] = False
    report = validate_pin(document)
    assert not report.ok
    assert any("not asserted intended" in problem for problem in report.problems)


def test_non_hex_commit_sha_is_rejected() -> None:
    document = load_pin()
    document["commit_sha"] = "not-a-sha"
    report = validate_pin(document)
    assert not report.ok
    assert any("commit_sha" in problem for problem in report.problems)
