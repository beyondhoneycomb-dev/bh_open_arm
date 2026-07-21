"""Acceptance ③ — the dummy opens no CAN socket.

Two guards, one static and one dynamic. Statically, no CAN symbol (`import can`,
`AF_CAN`, `PF_CAN`, …) appears anywhere in the package source. Dynamically, the
whole dummy lifecycle — construct, connect, observe, act, disconnect — and the
entire fault-injection library run inside a guard that raises the instant any
`AF_CAN` socket is requested, and the guard reports zero attempts. A control fixture
that does open an `AF_CAN` socket proves the guard is not vacuous.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from packages.lerobot_robot_openarm_dummy import (
    CanSocketOpenedError,
    DummyOpenArmRobot,
    DummyRobotConfig,
    check_package,
    forbid_can_sockets,
    scenario_library,
)
from packages.lerobot_robot_openarm_dummy.staticcheck import RULE_CAN_SYMBOL

_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "packages" / "lerobot_robot_openarm_dummy"

_HAS_AF_CAN = hasattr(socket, "AF_CAN")


def test_full_dummy_lifecycle_opens_no_can_socket(tmp_path: Path) -> None:
    """Constructing and driving the dummy attempts no AF_CAN socket."""
    with forbid_can_sockets() as report:
        robot = DummyOpenArmRobot(DummyRobotConfig(id="follower", calibration_dir=tmp_path))
        robot.connect()
        for _ in range(5):
            robot.get_observation()
        robot.send_action(dict.fromkeys(robot.action_features, 0.0))
        robot.disconnect()
    assert report.can_socket_attempts == 0


def test_fault_library_opens_no_can_socket(tmp_path: Path) -> None:
    """Every fault scenario runs without opening a CAN socket (bus-off is simulated)."""
    with forbid_can_sockets() as report:
        for scenario in scenario_library():
            scenario.run(tmp_path)
    assert report.can_socket_attempts == 0


@pytest.mark.skipif(not _HAS_AF_CAN, reason="platform has no AF_CAN to open")
def test_guard_bites_on_a_real_can_open() -> None:
    """The guard raises when code under it opens an AF_CAN socket (non-vacuous)."""
    with pytest.raises(CanSocketOpenedError), forbid_can_sockets():
        socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)


def test_guard_restores_socket_factory() -> None:
    """The guard restores the real socket factory on exit."""
    original = socket.socket
    with forbid_can_sockets():
        pass
    assert socket.socket is original


def test_package_source_has_no_can_symbol() -> None:
    """No CAN symbol appears in the package source (static half)."""
    can_violations = [v for v in check_package(_PACKAGE_ROOT) if v.rule == RULE_CAN_SYMBOL]
    assert can_violations == []
