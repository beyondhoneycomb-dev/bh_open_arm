"""Acceptance ⑧ — `use_velocity_and_torque` follower/leader check runs at session start (F24).

F24: an unset `use_velocity_and_torque` silently drops the torque channel. The check runs at
session start on both arms; an unset or false flag on either arm must raise before any data is
collected. "Unset" and "explicitly false" are the same failure — a missing key is the default-
off case F24 warns about.
"""

from __future__ import annotations

import pytest

from ops.telemetry.velocity_torque import (
    TorqueDataLossError,
    assert_velocity_and_torque_at_session_start,
    check_velocity_and_torque,
)

_BOTH_SET = ({"use_velocity_and_torque": True}, {"use_velocity_and_torque": True})


def test_both_arms_set_passes() -> None:
    """With both arms flagged, the session-start assertion does not raise."""
    follower, leader = _BOTH_SET
    assert_velocity_and_torque_at_session_start(follower, leader)
    result = check_velocity_and_torque(follower, leader)
    assert result.ok
    assert result.problems == ()


def test_follower_unset_raises_at_session_start() -> None:
    """A follower missing the key raises before data collection."""
    with pytest.raises(TorqueDataLossError):
        assert_velocity_and_torque_at_session_start({}, {"use_velocity_and_torque": True})


def test_leader_false_raises_at_session_start() -> None:
    """A leader with the flag explicitly false is the same failure as unset."""
    with pytest.raises(TorqueDataLossError):
        assert_velocity_and_torque_at_session_start(
            {"use_velocity_and_torque": True},
            {"use_velocity_and_torque": False},
        )


def test_both_arms_reported_when_both_bad() -> None:
    """The result names each arm that would lose torque, not just the first."""
    result = check_velocity_and_torque({}, {"use_velocity_and_torque": False})
    assert not result.ok
    assert not result.follower_ok
    assert not result.leader_ok
    assert len(result.problems) == 2
