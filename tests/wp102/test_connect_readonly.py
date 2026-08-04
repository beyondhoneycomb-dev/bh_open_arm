"""Acceptance ①(offline part)/⑪/⑬: torque-OFF bring-up, rest modal placement, connect-once.

The 16-motor hardware assertion of ① is deferred (see test_deferred_hardware); what runs
here is that the bring-up path leaves torque OFF, never auto-zeroes, places the rest-pose
confirmation on `set_zero` rather than `connect`, and refuses a second connect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.calibration.schema import ZeroMethod
from backend.can.lock import LockManager
from backend.can.lock.connect_guard import LockOrderingError
from packages.lerobot_robot_openarm.openarm_follower_oa import SessionError
from tests.wp102.conftest import HANDSHAKE_ENABLE


def commanded_enables(bus) -> list[str]:
    """Every enable the bring-up put in the log that was not the bus handshake.

    Matched on substring, not equality: the log carries arguments alongside the name
    (`enable_all(0xFC)`), so an equality test has no writer and passes against a bring-up
    that energises the arm — which is the exact failure this file exists to catch.
    """
    return [
        command for command in bus.commands if "enable" in command and command != HANDSHAKE_ENABLE
    ]


def test_connect_readonly_commands_no_torque(make_follower) -> None:
    """`connect_readonly()` opens the bus and commands no torque (FR-CON-062).

    The motors end up enabled regardless, because the bus handshake enables them. So the
    claim under test is the narrow one — nothing here asked for torque — and the handshake
    is asserted rather than ignored: an arm that is live after a "read-only" bring-up is
    the fact an operator needs, and a suite that stayed silent about it once already
    described a rig nobody has.
    """
    follower, bus = make_follower()
    follower.connect_readonly()
    assert follower.is_connected
    assert follower.is_torque_enabled is False
    assert commanded_enables(bus) == []
    assert HANDSHAKE_ENABLE in bus.commands


def test_connect_does_not_autozero_or_command_torque(make_follower) -> None:
    """`connect()` commands no torque and never emits a set-zero (FR-CON-061)."""
    follower, bus = make_follower()
    follower.connect(calibrate=True)  # even asked to calibrate, it must not zero
    assert follower.is_torque_enabled is False
    assert follower.is_calibrated is False
    assert "set_zero_position" not in bus.commands
    assert commanded_enables(bus) == []


def test_rest_modal_is_at_set_zero_not_connect(make_follower) -> None:
    """The rest-pose confirmation gates `set_zero`, not `connect` (FR-CON-063, ⑪).

    `connect_readonly()` takes no rest confirmation and succeeds; `set_zero()` refuses
    until rest is confirmed. A bring-up that demanded the modal at connect time — or a
    set_zero that skipped it — would fail one of these.
    """
    follower, _bus = make_follower()
    follower.connect_readonly()  # no rest argument accepted or required here
    with pytest.raises(Exception) as unrest:
        follower.set_zero(ZeroMethod.LEROBOT_HANGING, rest_confirmed=False)
    assert "rest" in str(unrest.value).lower()


def test_connect_once_per_session(make_follower) -> None:
    """A second connect this session is refused (01 FR-SYS-001, ⑬)."""
    follower, _bus = make_follower()
    follower.connect_readonly()
    with pytest.raises(SessionError):
        follower.connect_readonly()
    with pytest.raises(SessionError):
        follower.connect()


def test_set_zero_requires_connect_first(make_follower) -> None:
    """`set_zero()` before any connect is refused."""
    follower, _bus = make_follower()
    with pytest.raises(SessionError):
        follower.set_zero(ZeroMethod.HARDSTOP_BUMP, rest_confirmed=True)


def test_bus_opens_only_after_the_channel_lock_is_held(make_follower, tmp_path: Path) -> None:
    """A lock-guarded connect refuses to open the bus until the lock is held (01 FR-SYS-005)."""
    follower, bus = make_follower()
    manager = LockManager(lock_dir=str(tmp_path / "locks"))
    # No lock held: guarded_connect must refuse and never open the socket.
    with pytest.raises(LockOrderingError):
        follower.connect_readonly(lock_manager=manager)
    assert "connect" not in bus.commands

    other, other_bus = make_follower()
    assert manager.acquire_all([other.config.port]).ok
    other.connect_readonly(lock_manager=manager)
    assert other.is_connected
    manager.release_all()
