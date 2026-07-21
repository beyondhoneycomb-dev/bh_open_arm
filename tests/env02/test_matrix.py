"""WP-ENV-02 acceptance ①–③ — the target matrix validates and its fixtures fail."""

from __future__ import annotations

import copy
from typing import Any

from targets.matrix import load_matrix, validate_matrix


def _valid() -> dict[str, Any]:
    return copy.deepcopy(load_matrix())


def test_committed_matrix_is_valid() -> None:
    report = validate_matrix(load_matrix())
    assert report.ok, report.problems


def test_missing_fleet_target_is_reported() -> None:
    document = _valid()
    document["targets"] = [t for t in document["targets"] if t["target_id"] != "jetson_orin"]
    report = validate_matrix(document)
    assert not report.ok
    assert any("jetson_orin" in problem for problem in report.problems)


def test_deferred_without_reason_is_a_silent_failure() -> None:
    document = _valid()
    for target in document["targets"]:
        if target["target_id"] == "rtx_a6000":
            target["lock_resolution"]["reason"] = ""
    report = validate_matrix(document)
    assert not report.ok
    assert any("silent failure" in problem for problem in report.problems)


def test_blocked_path_predicate_must_resolve() -> None:
    document = _valid()
    document["targets"][0]["blocked_paths"][0]["predicate"] = "targets.guards.does_not_exist"
    report = validate_matrix(document)
    assert not report.ok
    assert any("does not resolve" in problem for problem in report.problems)


def test_missing_a100_h100_exclusion_is_reported() -> None:
    document = _valid()
    document["excluded"] = [e for e in document["excluded"] if e["target_id"] != "a100"]
    report = validate_matrix(document)
    assert not report.ok
    assert any("a100" in problem for problem in report.problems)
