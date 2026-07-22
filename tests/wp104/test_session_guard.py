"""Acceptance ②③④: the session enforces one connect, torque OFF, and the held lock.

The lock is a real `flock` in a temp dir (VFS-level, no CAN needed); the connect and
torque probe are injected, as they are on the rig. Only the real read is deferred.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.lock.connect_guard import LockOrderingError
from backend.can.lock.manager import LockManager
from backend.rtbench.session import (
    NotConnectedError,
    ReadOnlyMeasurementSession,
    RepeatedConnectError,
    TorqueEngagedError,
    TorqueState,
)

_IFACES = ("oa_fl", "oa_fr")
_MOTOR_IDS = tuple(range(16))


def _all_off() -> TorqueState:
    return TorqueState(enabled=dict.fromkeys(_MOTOR_IDS, False))


def _one_engaged() -> TorqueState:
    state = dict.fromkeys(_MOTOR_IDS, False)
    state[7] = True
    return TorqueState(enabled=state)


def _binding() -> str:
    return "bound"


def test_connect_without_the_lock_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    session = ReadOnlyMeasurementSession(manager, _IFACES, _binding, _all_off)
    with pytest.raises(LockOrderingError):
        session.connect()
    assert session.connect_call_count == 0


def test_single_connect_with_lock_and_torque_off_succeeds(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session = ReadOnlyMeasurementSession(manager, _IFACES, _binding, _all_off)
        assert session.connect() == "bound"
        assert session.connect_call_count == 1
        session.assert_publishable()
    finally:
        manager.release_all()


def test_second_connect_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session = ReadOnlyMeasurementSession(manager, _IFACES, _binding, _all_off)
        session.connect()
        with pytest.raises(RepeatedConnectError):
            session.connect()
        assert session.connect_call_count == 1
    finally:
        manager.release_all()


def test_connect_with_torque_engaged_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session = ReadOnlyMeasurementSession(manager, _IFACES, _binding, _one_engaged)
        with pytest.raises(TorqueEngagedError, match="7"):
            session.connect()
    finally:
        manager.release_all()


def test_publish_without_connect_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    try:
        session = ReadOnlyMeasurementSession(manager, _IFACES, _binding, _all_off)
        with pytest.raises(NotConnectedError):
            session.assert_publishable()
    finally:
        manager.release_all()


def test_publish_after_the_lock_is_released_is_refused(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=str(tmp_path))
    assert manager.acquire_all(_IFACES).ok
    session = ReadOnlyMeasurementSession(manager, _IFACES, _binding, _all_off)
    session.connect()
    manager.release_all()
    with pytest.raises(LockOrderingError):
        session.assert_publishable()


def test_torque_state_helpers() -> None:
    assert _all_off().all_off()
    assert _all_off().engaged_ids() == ()
    assert not _one_engaged().all_off()
    assert _one_engaged().engaged_ids() == (7,)
