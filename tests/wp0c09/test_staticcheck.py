"""Acceptance ①/④/⑨ static — the source bans hold, and they are not vacuous."""

from __future__ import annotations

from pathlib import Path

import sim.dryrun
from sim.dryrun.staticcheck import (
    RULE_CAN_SYMBOL,
    RULE_FABRICATED_GRANT,
    RULE_TWIN_SEND_ACTION,
    check_dryrun_tree,
    check_grant_construction,
    check_no_can,
    check_twin_no_send_action,
)

_DRYRUN_ROOT = Path(sim.dryrun.__file__).resolve().parent


def test_dryrun_tree_is_clean() -> None:
    """①/④/⑨ The real dry-run tree has no CAN symbol, no fabricated grant, no twin send."""
    assert check_dryrun_tree(_DRYRUN_ROOT) == ()


def test_fabricated_grant_check_bites() -> None:
    """④ Constructing a TransmissionGrant outside interlock.py is flagged."""
    source = (
        "from sim.dryrun.interlock import TransmissionGrant\n"
        "x = TransmissionGrant(k, v, True, 'o')\n"
    )
    findings = check_grant_construction(source, "sim/dryrun/rogue.py")
    assert [f.rule for f in findings] == [RULE_FABRICATED_GRANT]


def test_grant_check_ignores_the_interlock_itself() -> None:
    """④ interlock.py is the one file allowed to construct the grant."""
    source = "x = TransmissionGrant(_GRANT_KEY, v, True, 'o')\n"
    assert check_grant_construction(source, "sim/dryrun/interlock.py") == []


def test_twin_send_action_check_bites() -> None:
    """⑨ A send_action reference in a twin-named source is flagged."""
    source = "def mirror(robot):\n    robot.send_action({})\n"
    findings = check_twin_no_send_action(source, "sim/dryrun/twin.py")
    assert [f.rule for f in findings] == [RULE_TWIN_SEND_ACTION]


def test_can_symbol_check_bites() -> None:
    """① A CAN import in dry-run source is flagged."""
    findings = check_no_can("import can\n", "sim/dryrun/rogue.py")
    assert [f.rule for f in findings] == [RULE_CAN_SYMBOL]
