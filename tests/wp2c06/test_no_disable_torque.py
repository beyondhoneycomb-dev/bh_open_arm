"""The reaction path holds no `disable_torque`, and the reused scan still bites.

Three halves, all running on this host. First the premise itself: the actuation reaction path
— and this bench's own tree — are free of `disable_torque`, so the precondition passes (the
reaction is a continuous STOP_HOLD MIT frame, `02b` WP-2C-05). Second the WP-BOOT-03
discipline: a scan is only trustworthy if a violation fixture proves it still catches the
symbol, so a temporary tree that *does* hold `disable_torque` must be refused. Without that
second half a green precondition could mean "the symbol is absent" or "the scan is broken",
and those are not the same.

The third is coverage, and it is the one the other two rest on. An empty violation list from
a root that does not exist reads identically to an empty violation list from a clean reaction
path, so these pin what the default root is, that it resolves the same from any working
directory, and that the file count the check reports is what the scan actually parsed. A
safety scan that scanned nothing has not passed; it has not run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.reaction_bench import (
    DEFAULT_REACTION_PATH_ROOT,
    REACTION_PATH_TREE,
    DisableTorqueOnReactionPathError,
    ReactionPathScanEmptyError,
    assert_no_disable_torque,
    check_no_disable_torque,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# The declared reaction path, spelled out here rather than read back from the package, so
# this file states the value the default must have instead of comparing the constant to
# itself.
DECLARED_REACTION_PATH_TREE = Path("backend/actuation")


def test_declared_reaction_path_tree_is_the_actuation_spine() -> None:
    assert REACTION_PATH_TREE == DECLARED_REACTION_PATH_TREE


def test_default_root_resolves_the_declared_tree_under_the_repo() -> None:
    assert DEFAULT_REACTION_PATH_ROOT.is_absolute()
    assert DEFAULT_REACTION_PATH_ROOT == REPO_ROOT / DECLARED_REACTION_PATH_TREE
    assert DEFAULT_REACTION_PATH_ROOT.is_dir()


def test_actuation_reaction_path_has_no_disable_torque() -> None:
    check = check_no_disable_torque(DEFAULT_REACTION_PATH_ROOT)
    assert check.passed, f"disable_torque on the reaction path: {check.violations}"
    assert check.as_record()["reused_scan"] == "backend.actuation.staticcheck.find_disable_torque"


def test_the_default_scan_covers_every_file_of_the_declared_tree() -> None:
    # The count is compared against an independent walk of the declared tree, so repointing
    # the default at an empty or absent directory fails here instead of reporting a pass.
    expected = [
        path
        for path in (REPO_ROOT / DECLARED_REACTION_PATH_TREE).rglob("*.py")
        if not any(part.startswith(".") for part in path.parts)
    ]
    assert expected, "the declared reaction path holds no Python file"
    check = check_no_disable_torque()
    assert check.scanned_file_count == len(expected)
    assert check.as_record()["scanned_file_count"] == len(expected)


def test_the_record_names_the_root_relative_to_the_repo() -> None:
    # The artifact is read on machines that are not this one, so the root it publishes is
    # the path inside the repo rather than this checkout's absolute location.
    record = check_no_disable_torque().as_record()
    assert record["root"] == DECLARED_REACTION_PATH_TREE.as_posix()


def test_a_root_outside_the_repo_is_named_absolutely(tmp_path: Path) -> None:
    # Nothing outside the tree has a repo-relative name, and truncating one would publish a
    # path that reads as a directory inside the repo the scan never opened.
    (tmp_path / "hold.py").write_text("def react(bus):\n    bus.mit_hold()\n", encoding="utf-8")
    record = check_no_disable_torque(tmp_path).as_record()
    assert record["root"] == tmp_path.resolve().as_posix()


def test_bench_own_tree_has_no_disable_torque() -> None:
    check = check_no_disable_torque(REPO_ROOT / "backend" / "reaction_bench")
    assert check.passed, f"reaction_bench introduced disable_torque: {check.violations}"


def test_assert_no_disable_torque_returns_the_passing_check() -> None:
    check = assert_no_disable_torque(DEFAULT_REACTION_PATH_ROOT)
    assert check.passed
    assert check.root == DEFAULT_REACTION_PATH_ROOT


def test_the_default_scan_is_the_same_from_any_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The operator runs the CLI from wherever they are standing. A cwd-relative default
    # resolves to nothing outside the repo, and nothing is what a clean path looks like.
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
    with pytest.raises(ReactionPathScanEmptyError):
        assert_no_disable_torque(Path("does/not/exist"))


def test_a_tree_with_no_python_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a reaction path\n", encoding="utf-8")
    with pytest.raises(ReactionPathScanEmptyError):
        assert_no_disable_torque(tmp_path)


def test_an_exclusion_that_covers_everything_is_refused(tmp_path: Path) -> None:
    covered = tmp_path / "covered"
    covered.mkdir()
    (covered / "hold.py").write_text("def react(bus):\n    bus.mit_hold()\n", encoding="utf-8")
    with pytest.raises(ReactionPathScanEmptyError):
        assert_no_disable_torque(tmp_path, exclude=[covered])


def _write_reaction_path_with_disable_torque(root: Path) -> None:
    """Write a fixture reaction-path module that cuts torque, to prove the scan bites.

    Args:
        root: Directory to write the violating module into.
    """
    (root / "cutting_reaction.py").write_text(
        "def react(bus):\n    bus.disable_torque()\n",
        encoding="utf-8",
    )


def test_violation_fixture_is_caught_by_the_scan(tmp_path: Path) -> None:
    _write_reaction_path_with_disable_torque(tmp_path)
    check = check_no_disable_torque(tmp_path)
    assert not check.passed
    assert any("disable_torque" in str(violation) for violation in check.violations)


def test_violation_fixture_refuses_the_precondition(tmp_path: Path) -> None:
    _write_reaction_path_with_disable_torque(tmp_path)
    with pytest.raises(DisableTorqueOnReactionPathError):
        assert_no_disable_torque(tmp_path)


def test_reported_count_is_what_the_scan_parsed(tmp_path: Path) -> None:
    # Every file below holds exactly one `disable_torque`, so one violation per parsed file
    # is what the reused scan returns. Equality between the two pins the count to the scan's
    # own traversal — hidden directories and the excluded directory are read by neither.
    cutting = "def react(bus):\n    bus.disable_torque()\n"
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
