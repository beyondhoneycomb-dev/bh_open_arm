"""Shared fixtures for WP-1-02: a CAN-free bus double and a follower factory.

Every offline acceptance runs the real follower flow against `FakeDamiaoBus`, which
records the CAN commands it is asked to send and never opens a socket. The settle
sleep in `set_zero` is a hardware-timing concern with no meaning offline, so it is
patched to a no-op for the whole package (autouse) to keep the suite fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.calibration.schema import MOTOR_ORDER
from contracts.plugin.config import Side
from packages.lerobot_robot_openarm import openarm_follower_oa
from packages.lerobot_robot_openarm.config_oa import OaOpenArmFollowerConfig
from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower


class FakeDamiaoBus:
    """A CAN-free stand-in for `DamiaoMotorsBus` that records the commands it is sent.

    Ownership: holds only in-memory connection state, a command log, and a per-motor
    position it reports back. It opens no socket and enables no torque — it exists so
    the bring-up and zero flow can be driven with no hardware present.
    """

    def __init__(self, connect_fails: bool = False, position_deg: float = 0.0) -> None:
        """Build the fake bus.

        Args:
            connect_fails: When True, `connect()` raises — used to provoke a partial
                bimanual connect.
            position_deg: The joint angle every motor reports on a readback.
        """
        self._connected = False
        self._connect_fails = connect_fails
        self._position_deg = position_deg
        self.commands: list[str] = []

    @property
    def is_connected(self) -> bool:
        """Whether the fake bus is 'open'."""
        return self._connected

    def connect(self, handshake: bool = True) -> None:
        """Open the bus (register motors); raise when armed to fail."""
        if self._connect_fails:
            raise RuntimeError("fake bus: CAN interface unavailable")
        self._connected = True
        self.commands.append("connect")

    def disconnect(self, disable_torque: bool = False) -> None:
        """Close the bus."""
        self._connected = False
        self.commands.append(f"disconnect(disable_torque={disable_torque})")

    def disable_torque(self, motors: object = None) -> None:
        """Record a 0xFD disable-torque command."""
        self.commands.append("disable_torque")

    def set_zero_position(self, motors: object = None) -> None:
        """Record a 0xFE set-zero command and re-base the reported position to 0."""
        self.commands.append("set_zero_position")
        self._position_deg = 0.0

    def sync_read_all_states(self) -> dict[str, dict[str, float]]:
        """Return a readback frame for every motor at the configured position."""
        self.commands.append("sync_read_all_states")
        return {
            motor: {"position": self._position_deg, "velocity": 0.0, "torque": 0.0}
            for motor in MOTOR_ORDER
        }


@pytest.fixture(autouse=True)
def _no_settle_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the set-zero settle a no-op so the offline suite does not wait on it."""
    monkeypatch.setattr(openarm_follower_oa.time, "sleep", lambda _seconds: None)


@pytest.fixture
def make_follower(tmp_path: Path):
    """Return a factory building a fixture-bus `OaOpenArmFollower` in a temp calib dir."""

    def _make(
        side: Side = Side.LEFT,
        robot_id: str = "test_arm",
        connect_fails: bool = False,
        position_deg: float = 0.0,
    ) -> tuple[OaOpenArmFollower, FakeDamiaoBus]:
        bus = FakeDamiaoBus(connect_fails=connect_fails, position_deg=position_deg)
        config = OaOpenArmFollowerConfig(side=side, id=robot_id, calibration_dir=tmp_path)
        return OaOpenArmFollower(config, bus=bus), bus

    return _make
