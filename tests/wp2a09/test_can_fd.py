"""Item ③ — an unset CAN-FD link blocks startup. RUNS HERE.

Reuses the `WP-0B-02` verifier: a CAN-2.0 link (fd off) fails `validate_link`, so
torque-ON is blocked rather than waved through on a link that would break communication
silently (`01` §2.18 trap 5).
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.can.lock import LockState
from backend.preflight import TorqueOnBlockedError, authorize_torque_on, check_can_fd
from backend.preflight.preflight import JogSessionPreflight
from tests.wp2a09.builders import link_fd_off, link_fd_on, passing_inputs


def test_fd_off_blocks() -> None:
    result = check_can_fd(link_fd_off())
    assert not result.passed
    assert "fd" in result.detail


def test_unread_link_blocks_fail_closed() -> None:
    assert not check_can_fd(None).passed


def test_fd_on_passes() -> None:
    assert check_can_fd(link_fd_on()).passed


def test_fd_off_blocks_torque_end_to_end(self_held_lock_state: LockState) -> None:
    inputs = dataclasses.replace(passing_inputs(self_held_lock_state), link=link_fd_off())
    report = JogSessionPreflight().run(inputs)
    assert not report.may_enable_torque
    with pytest.raises(TorqueOnBlockedError):
        authorize_torque_on(report)
