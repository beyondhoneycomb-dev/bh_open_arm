"""Item ④ — a writer lock this process does not hold blocks, naming the holder PID. RUNS HERE.

`flock` only arbitrates between separate processes, so the foreign-holder case is driven
with a real second process (`WP-0B-01`'s contention harness). The refusal must name the
holder PID (`02` FR-CON-010), and a free-but-unheld lock must block too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.lock import LockManager, LockState
from backend.can.lock.harness import HeldLockProcess
from backend.preflight import TorqueOnBlockedError, authorize_torque_on, check_writer_lock
from backend.preflight.preflight import JogSessionPreflight
from tests.wp2a09.builders import TEST_IFACE, passing_inputs


def test_self_held_passes(self_held_lock_state: LockState) -> None:
    assert check_writer_lock(self_held_lock_state).passed


def test_foreign_holder_blocks_and_names_pid(tmp_path: Path) -> None:
    with HeldLockProcess(str(tmp_path), [TEST_IFACE]) as holder:
        state = LockManager(lock_dir=str(tmp_path)).lock_state([TEST_IFACE])[0]
        result = check_writer_lock(state)
        assert not result.passed
        assert str(holder.pid) in result.detail


def test_free_lock_blocks(tmp_path: Path) -> None:
    state = LockManager(lock_dir=str(tmp_path)).lock_state([TEST_IFACE])[0]
    result = check_writer_lock(state)
    assert not result.passed


def test_foreign_holder_blocks_torque_end_to_end(tmp_path: Path) -> None:
    with HeldLockProcess(str(tmp_path), [TEST_IFACE]) as holder:
        state = LockManager(lock_dir=str(tmp_path)).lock_state([TEST_IFACE])[0]
        report = JogSessionPreflight().run(passing_inputs(state))
        assert not report.may_enable_torque
        with pytest.raises(TorqueOnBlockedError) as blocked:
            authorize_torque_on(report)
        assert str(holder.pid) in str(blocked.value)
