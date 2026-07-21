"""Acceptance ⑤⑥ — no LeRobot in-tree loop import, no CLI subprocess spawn.

Static, over the package's own source. The package must contain zero imports of a
LeRobot in-tree loop (`lerobot.scripts.*`, where `lerobot_teleoperate.py` /
`lerobot_record.py` live — 01 FR-SYS-003) and zero CLI-spawn symbols (`subprocess`,
`os.system` / `os.exec*` / `os.spawn*`, `pty.spawn` — 01 FR-SYS-002). Fixtures that
each carry one banned form prove the checks are not vacuous, and a clean fixture
importing only the LeRobot ABCs proves they do not over-fire.
"""

from __future__ import annotations

from pathlib import Path

from packages.lerobot_robot_openarm_dummy.staticcheck import (
    RULE_CLI_SPAWN,
    RULE_INTREE_LOOP_IMPORT,
    check_package,
    check_source,
)

_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "packages" / "lerobot_robot_openarm_dummy"


def test_package_imports_no_intree_loop() -> None:
    """No `lerobot.scripts.*` in-tree loop is imported anywhere in the package (⑤)."""
    loop_imports = [v for v in check_package(_PACKAGE_ROOT) if v.rule == RULE_INTREE_LOOP_IMPORT]
    assert loop_imports == []


def test_package_spawns_no_cli() -> None:
    """No subprocess-spawn symbol appears anywhere in the package (⑥)."""
    spawns = [v for v in check_package(_PACKAGE_ROOT) if v.rule == RULE_CLI_SPAWN]
    assert spawns == []


def test_package_is_wholly_clean() -> None:
    """The package trips none of the three source bans."""
    assert check_package(_PACKAGE_ROOT) == ()


def test_intree_loop_import_is_detected() -> None:
    """Importing a LeRobot in-tree loop is flagged (the ⑤ check bites)."""
    findings = check_source("from lerobot.scripts.lerobot_record import record_loop\n")
    assert [f.rule for f in findings] == [RULE_INTREE_LOOP_IMPORT]


def test_intree_teleop_import_is_detected() -> None:
    """Importing the teleoperate loop is flagged too."""
    findings = check_source("import lerobot.scripts.lerobot_teleoperate\n")
    assert [f.rule for f in findings] == [RULE_INTREE_LOOP_IMPORT]


def test_subprocess_import_is_detected() -> None:
    """A `subprocess` import is flagged as a CLI spawn (the ⑥ check bites)."""
    findings = check_source("import subprocess\n")
    assert [f.rule for f in findings] == [RULE_CLI_SPAWN]


def test_os_system_is_detected() -> None:
    """An `os.system` call is flagged as a CLI spawn."""
    findings = check_source("import os\nos.system('ls')\n")
    assert RULE_CLI_SPAWN in [f.rule for f in findings]


def test_os_spawn_from_import_is_detected() -> None:
    """A direct `from os import execv` is flagged as a CLI spawn."""
    findings = check_source("from os import execv\n")
    assert [f.rule for f in findings] == [RULE_CLI_SPAWN]


def test_lerobot_abc_import_is_not_flagged() -> None:
    """Importing the LeRobot ABCs is legitimate and trips nothing."""
    clean = (
        "from lerobot.robots.robot import Robot\n"
        "from lerobot.teleoperators.teleoperator import Teleoperator\n"
    )
    assert check_source(clean) == ()
