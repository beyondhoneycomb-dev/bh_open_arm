"""The reaction path holds no `disable_torque`, and the reused scan still bites.

Two halves, both running on this host. First the premise itself: the actuation reaction path
— and this bench's own tree — are free of `disable_torque`, so the precondition passes (the
reaction is a continuous STOP_HOLD MIT frame, `02b` WP-2C-05). Second the WP-BOOT-03
discipline: a scan is only trustworthy if a violation fixture proves it still catches the
symbol, so a temporary tree that *does* hold `disable_torque` must be refused. Without that
second half a green precondition could mean "the symbol is absent" or "the scan is broken",
and those are not the same.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.reaction_bench import (
    DEFAULT_REACTION_PATH_ROOT,
    DisableTorqueOnReactionPathError,
    assert_no_disable_torque,
    check_no_disable_torque,
)


def test_actuation_reaction_path_has_no_disable_torque() -> None:
    check = check_no_disable_torque(DEFAULT_REACTION_PATH_ROOT)
    assert check.passed, f"disable_torque on the reaction path: {check.violations}"
    assert check.as_record()["reused_scan"] == "backend.actuation.staticcheck.find_disable_torque"


def test_bench_own_tree_has_no_disable_torque() -> None:
    check = check_no_disable_torque(Path("backend/reaction_bench"))
    assert check.passed, f"reaction_bench introduced disable_torque: {check.violations}"


def test_assert_no_disable_torque_returns_the_passing_check() -> None:
    check = assert_no_disable_torque(DEFAULT_REACTION_PATH_ROOT)
    assert check.passed
    assert check.root == DEFAULT_REACTION_PATH_ROOT


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
