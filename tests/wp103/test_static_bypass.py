"""Acceptance ① / ⑬ — the enforcement point has no bypass, the stop path no torque cut.

Both are absences, and an absence is only honestly checked statically: a runtime test
shows the paths it happened to run, never the one a future edit adds. So these are AST
scans, each paired with a violation fixture proving the scan bites.

- ① The single gateway is un-bypassable: no CAN write symbol (`mit_control_batch` /
  `_mit_control_batch` / `CanWriter`) appears outside the owning actuation tree, so
  the follower's `send_action` cannot reach past the gateway for the bus.
- ⑬ The stop path holds, never cuts torque: `disable_torque` appears nowhere in the
  actuation spine (`04` NFR-MAN-002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.actuation import find_disable_torque, find_producer_can_access

_REPO = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ACTUATION_TREE = _REPO / "backend" / "actuation"
_FOLLOWER_PACKAGE = _REPO / "packages" / "lerobot_robot_openarm"

_CAN_WRITE_SYMBOLS = {"mit_control_batch", "_mit_control_batch", "CanWriter", "FakeCanWriter"}


def test_follower_package_has_no_can_write_bypass() -> None:
    """The follower package names no CAN write symbol — send_action cannot bypass (①)."""
    assert find_producer_can_access(_FOLLOWER_PACKAGE) == []


def test_bypass_fixture_is_flagged_clean_one_is_not() -> None:
    """The bypassing follower is caught; the delegating one beside it is not (①)."""
    violations = find_producer_can_access(_FIXTURES)
    flagged = {violation.path.name for violation in violations}
    assert "bypass_bus_write.py" in flagged
    assert "clean_delegation.py" not in flagged
    assert {violation.symbol for violation in violations} & _CAN_WRITE_SYMBOLS


def test_owning_actuation_tree_is_not_over_flagged() -> None:
    """The scan exempts the owner: the gateway's own CAN writer use is not a bypass (①)."""
    assert find_producer_can_access(_ACTUATION_TREE) == []


def test_stop_path_has_no_disable_torque() -> None:
    """No file in the actuation spine references `disable_torque` (⑬)."""
    assert find_disable_torque(_ACTUATION_TREE) == []


@pytest.mark.fixture_corpus
def test_disable_torque_fixture_is_flagged() -> None:
    """The torque-cutting stop fixture is caught — the ⑬ scan bites."""
    violations = find_disable_torque(_FIXTURES)
    flagged = {violation.path.name for violation in violations}
    assert "disable_torque_stop.py" in flagged
    assert all(violation.symbol == "disable_torque" for violation in violations)
