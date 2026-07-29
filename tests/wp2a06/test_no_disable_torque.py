"""Acceptance ②: the stop path holds no `disable_torque`, and the reused scan still bites.

Three halves, all running on this host. First the premise itself: the real actuation stop
path — and this bench's own tree — are free of `disable_torque`, so the precondition passes
(`04` NFR-MAN-002). Second the WP-BOOT-03 discipline: a scan is only trustworthy if a
violation fixture proves it still catches the symbol, so a temporary tree that *does* hold
`disable_torque` must be refused. Without that second half a green precondition could mean
"the symbol is absent" or "the scan is broken", and those are not the same.

The third is coverage, and it is the one the other two rest on. An empty violation list
from a root that does not exist reads identically to an empty violation list from a clean
stop path, so these pin what the default root is, that it resolves the same from any
working directory, and that the file count the check reports is what the scan actually
parsed. A safety scan that scanned nothing has not passed; it has not run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.stopbench import (
    DEFAULT_STOP_PATH_ROOT,
    STOP_PATH_TREE,
    DisableTorqueOnStopPathError,
    StopPathScanEmptyError,
    assert_no_disable_torque,
    check_no_disable_torque,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# The declared stop path, spelled out here rather than read back from the package, so this
# file states the value the default must have instead of comparing the constant to itself.
DECLARED_STOP_PATH_TREE = Path("backend/actuation")


def test_declared_stop_path_tree_is_the_actuation_spine() -> None:
    assert STOP_PATH_TREE == DECLARED_STOP_PATH_TREE


def test_default_root_resolves_the_declared_tree_under_the_repo() -> None:
    assert DEFAULT_STOP_PATH_ROOT.is_absolute()
    assert DEFAULT_STOP_PATH_ROOT == REPO_ROOT / DECLARED_STOP_PATH_TREE
    assert DEFAULT_STOP_PATH_ROOT.is_dir()


def test_actuation_stop_path_has_no_disable_torque() -> None:
    check = check_no_disable_torque(DEFAULT_STOP_PATH_ROOT)
    assert check.passed, f"disable_torque on the stop path: {check.violations}"
    assert check.as_record()["reused_scan"] == "backend.actuation.staticcheck.find_disable_torque"


def test_the_default_scan_covers_every_file_of_the_declared_tree() -> None:
    # The count is compared against an independent walk of the declared tree, so repointing
    # the default at an empty or absent directory fails here instead of reporting a pass.
    expected = [
        path
        for path in (REPO_ROOT / DECLARED_STOP_PATH_TREE).rglob("*.py")
        if not any(part.startswith(".") for part in path.parts)
    ]
    assert expected, "the declared stop path holds no Python file"
    check = check_no_disable_torque()
    assert check.scanned_file_count == len(expected)
    assert check.as_record()["scanned_file_count"] == len(expected)


def test_bench_own_tree_has_no_disable_torque() -> None:
    check = check_no_disable_torque(REPO_ROOT / "backend" / "stopbench")
    assert check.passed, f"stopbench introduced disable_torque: {check.violations}"


def test_assert_no_disable_torque_returns_the_passing_check() -> None:
    check = assert_no_disable_torque(DEFAULT_STOP_PATH_ROOT)
    assert check.passed
    assert check.root == DEFAULT_STOP_PATH_ROOT


def test_the_default_scan_is_the_same_from_any_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The operator runs the CLI from wherever they are standing. A cwd-relative default
    # resolves to nothing outside the repo, and nothing is what a clean stop path looks like.
    from_repo = check_no_disable_torque()
    monkeypatch.chdir(tmp_path)
    from_elsewhere = check_no_disable_torque()
    assert from_elsewhere.scanned_file_count == from_repo.scanned_file_count
    assert from_elsewhere.scanned_file_count > 0
    assert from_elsewhere.passed


def test_a_missing_root_is_not_a_pass() -> None:
    check = check_no_disable_torque(Path("does/not/exist"))
    assert check.scanned_file_count == 0
    assert not check.violations
    assert not check.passed
    assert check.as_record()["passed"] is False


def test_a_missing_root_is_refused() -> None:
    with pytest.raises(StopPathScanEmptyError):
        assert_no_disable_torque(Path("does/not/exist"))


def test_a_tree_with_no_python_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a stop path\n", encoding="utf-8")
    with pytest.raises(StopPathScanEmptyError):
        assert_no_disable_torque(tmp_path)


def test_an_exclusion_that_covers_everything_is_refused(tmp_path: Path) -> None:
    covered = tmp_path / "covered"
    covered.mkdir()
    (covered / "hold.py").write_text("def stop(bus):\n    bus.mit_hold()\n", encoding="utf-8")
    with pytest.raises(StopPathScanEmptyError):
        assert_no_disable_torque(tmp_path, exclude=[covered])


def _write_stop_path_with_disable_torque(root: Path) -> None:
    """Write a fixture stop-path module that cuts torque, to prove the scan bites.

    Args:
        root: Directory to write the violating module into.
    """
    (root / "cutting_stop.py").write_text(
        "def stop(bus):\n    bus.disable_torque()\n",
        encoding="utf-8",
    )


def test_violation_fixture_is_caught_by_the_scan(tmp_path: Path) -> None:
    _write_stop_path_with_disable_torque(tmp_path)
    check = check_no_disable_torque(tmp_path)
    assert not check.passed
    assert any("disable_torque" in str(violation) for violation in check.violations)


def test_violation_fixture_refuses_the_precondition(tmp_path: Path) -> None:
    _write_stop_path_with_disable_torque(tmp_path)
    with pytest.raises(DisableTorqueOnStopPathError):
        assert_no_disable_torque(tmp_path)


def test_reported_count_is_what_the_scan_parsed(tmp_path: Path) -> None:
    # Every file below holds exactly one `disable_torque`, so one violation per parsed file
    # is what the reused scan returns. Equality between the two pins the count to the scan's
    # own traversal — hidden directories and the excluded directory are read by neither.
    cutting = "def stop(bus):\n    bus.disable_torque()\n"
    (tmp_path / "top.py").write_text(cutting, encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "deep.py").write_text(cutting, encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "ignored.py").write_text(cutting, encoding="utf-8")
    skipped = tmp_path / "skipped"
    skipped.mkdir()
    (skipped / "also_ignored.py").write_text(cutting, encoding="utf-8")

    check = check_no_disable_torque(tmp_path, exclude=[skipped])
    assert check.scanned_file_count == 2
    assert len(check.violations) == check.scanned_file_count
