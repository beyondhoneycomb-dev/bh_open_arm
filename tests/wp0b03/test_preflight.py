"""Preflight occupancy check (`02` FR-CON-011): writer occupancy blocks, readers warn.

Uses the real WP-0B-01 `LockManager` against a temp lock directory — ``flock`` is
VFS-level, so writer occupancy is fully reproducible here without any CAN hardware.
The reader side is fed synthetic rcvlist captures. This exercises the reader/writer
asymmetry of `01` FR-SYS-007: only a foreign writer blocks connect.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.preflight import PreflightCheck
from backend.can.lock import LockManager
from backend.can.lock.harness import HeldLockProcess
from tests.wp0b03.synth import make_rcvlist_all


def _preflight(lock_dir: str) -> PreflightCheck:
    """Build a preflight check bound to a temp lock dir, expecting one own listener."""
    return PreflightCheck(
        iface="vcan0",
        lock_manager=LockManager(lock_dir=lock_dir),
        listener_check=RxListenerCheck("vcan0", expected_own_listeners=1),
    )


def test_free_bus_may_proceed(tmp_path: Path) -> None:
    """No foreign writer and no excess listeners: preflight clears connect."""
    report = _preflight(str(tmp_path)).run(make_rcvlist_all({"vcan0": 1}))
    assert not report.writer_occupied
    assert report.listener_warning is None
    assert report.may_proceed


def test_foreign_writer_blocks(tmp_path: Path) -> None:
    """A second process holding the writer lock is a hard occupancy: connect blocks."""
    with HeldLockProcess(str(tmp_path), ["vcan0"]) as holder:
        report = _preflight(str(tmp_path)).run(make_rcvlist_all({"vcan0": 1}))
        assert report.writer_occupied
        assert report.writer_holder is not None
        assert report.writer_holder.holder_pid == holder.pid
        assert not report.may_proceed


def test_extra_listener_warns_but_does_not_block(tmp_path: Path) -> None:
    """Extra listeners are soft occupancy: a WARN is surfaced but connect may proceed."""
    report = _preflight(str(tmp_path)).run(make_rcvlist_all({"vcan0": 2}))
    assert not report.writer_occupied
    assert report.listener_warning is not None
    assert report.listener_warning.excess == 1
    assert report.may_proceed


def test_preflight_probe_leaves_lock_free(tmp_path: Path) -> None:
    """The non-blocking probe must not itself occupy the lock it checks."""
    check = _preflight(str(tmp_path))
    check.run(make_rcvlist_all({"vcan0": 1}))
    # A real acquirer must still be able to take the lock the preflight probed.
    manager = LockManager(lock_dir=str(tmp_path))
    result = manager.acquire_all(["vcan0"])
    assert result.ok
    manager.release_all()
