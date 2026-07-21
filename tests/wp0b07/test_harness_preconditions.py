"""The read harness enforces its three preconditions: lock held, link verified, torque OFF.

All run here. The lock is `flock` (VFS-level, no CAN needed), so a temp lock dir
reproduces the full ordering rule; the link verification (WP-0B-02) runs on an
injected parsed state. The torque-OFF assertion (`12` FR-SAF-075) is driven by an
injected probe; on the rig that probe reads real enable state, which is the only
deferred part of this check.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from backend.can.link.constants import (
    ACTIVE_STATE,
    BUS_OFF_STATE,
    RECOMMENDED_TXQUEUELEN,
    REQUIRED_BITRATE,
    REQUIRED_DBITRATE,
    REQUIRED_FD,
)
from backend.can.link.parser import LinkState
from backend.can.lock.connect_guard import LockOrderingError
from backend.can.lock.manager import LockManager
from backend.can.rid.dump import parse_dump
from backend.can.rid.harness import (
    LinkNotVerifiedError,
    RidReadHarness,
    TorqueEngagedError,
    TorqueState,
)
from backend.can.rid.motor_limits import MotorType
from backend.can.rid.reader import FixtureRidReader
from backend.can.rid.registers import RID_TMAX
from tests.wp0b07 import rid_fixtures as fx

_IFACE = "oa_fl"
_MOTOR_IDS = (0x05, 0x07)
_RIDS = (RID_TMAX,)


def _reader() -> FixtureRidReader:
    dump = parse_dump(
        fx.dump(
            _IFACE,
            {
                0x05: fx.healthy_motor(MotorType.DM4310, 1000),
                0x07: fx.healthy_motor(MotorType.DM4310, 1000),
            },
        )
    )
    return FixtureRidReader({_IFACE: dump})


def _all_off(motor_ids: Sequence[int]) -> TorqueState:
    return TorqueState(enabled=dict.fromkeys(motor_ids, False))


def _verified_link(iface: str) -> LinkState:
    return LinkState(
        iface=iface,
        fd=REQUIRED_FD,
        bitrate=REQUIRED_BITRATE,
        dbitrate=REQUIRED_DBITRATE,
        state=ACTIVE_STATE,
        txqueuelen=RECOMMENDED_TXQUEUELEN,
    )


def test_read_without_lock_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    harness = RidReadHarness(manager, _reader(), _all_off, _verified_link)
    with pytest.raises(LockOrderingError):
        harness.read(_IFACE, _MOTOR_IDS, _RIDS)


def test_read_with_lock_link_and_torque_off_returns_dump(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all([_IFACE]).ok
    try:
        harness = RidReadHarness(manager, _reader(), _all_off, _verified_link)
        dump = harness.read(_IFACE, _MOTOR_IDS, _RIDS)
        assert dump.motor_ids() == _MOTOR_IDS
        assert dump.motors[0x07].decoded(RID_TMAX).value == pytest.approx(10.0)
    finally:
        manager.release_all()


def test_read_over_unverified_link_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all([_IFACE]).ok
    try:

        def _bus_off(iface: str) -> LinkState:
            # A BUS-OFF link opens the socket but corrupts every frame (01 §2.18 trap 5).
            return LinkState(
                iface=iface,
                fd=REQUIRED_FD,
                bitrate=REQUIRED_BITRATE,
                dbitrate=REQUIRED_DBITRATE,
                state=BUS_OFF_STATE,
                txqueuelen=RECOMMENDED_TXQUEUELEN,
            )

        harness = RidReadHarness(manager, _reader(), _all_off, _bus_off)
        with pytest.raises(LinkNotVerifiedError, match="link verification failed"):
            harness.read(_IFACE, _MOTOR_IDS, _RIDS)
    finally:
        manager.release_all()


def test_read_with_torque_engaged_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all([_IFACE]).ok
    try:

        def _one_engaged(motor_ids: Sequence[int]) -> TorqueState:
            state = dict.fromkeys(motor_ids, False)
            state[0x07] = True
            return TorqueState(enabled=state)

        harness = RidReadHarness(manager, _reader(), _one_engaged, _verified_link)
        with pytest.raises(TorqueEngagedError, match="0x7|7"):
            harness.read(_IFACE, _MOTOR_IDS, _RIDS)
    finally:
        manager.release_all()


def test_torque_state_helpers() -> None:
    off = TorqueState(enabled={0x05: False, 0x07: False})
    assert off.all_off()
    assert off.engaged_ids() == ()
    on = TorqueState(enabled={0x05: False, 0x07: True})
    assert not on.all_off()
    assert on.engaged_ids() == (0x07,)
