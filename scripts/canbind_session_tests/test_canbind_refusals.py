"""The three things that must stop a round before a socket exists, and one that voids a reading.

Every refusal here is ordered against the same instant: `DamiaoMotorsBus.connect()` handshakes
each registered motor with 0xFC, so the arms are live from the socket. A check that fires after
it is a check that fires too late — the operator has already had an energized arm handed to them
without being told.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from backend.can.lock import LockManager
from backend.endeffector import SIDE_LEFT
from scripts import canbind_session as session
from scripts.canbind_session_tests.canbind_doubles import (
    INTERFACE_A,
    RESTING_ANGLE_DEG,
    FakeChannelBus,
    SilentMotorBus,
    channel,
    channel_lister,
    lock_manager_factory,
    two_channels,
)

DOWN_STATE = "STOPPED"


@pytest.fixture
def motor_names() -> tuple[str, ...]:
    """The seven arm joints every channel is registered with."""
    return session.identification_motor_names()


@pytest.fixture
def free_locks(tmp_path: Path) -> Iterator[LockManager]:
    """A lock manager over a temporary lock directory, released at the end of the test."""
    manager = LockManager(lock_dir=str(tmp_path))
    yield manager
    manager.release_all()


def _run_argv(captures: Path) -> list[str]:
    """The argv `--run` is given, minus the acknowledgement flag."""
    return ["--arm", SIDE_LEFT, "--captures", str(captures), "--run"]


def _refuse_to_spawn(config: session.SessionConfig, start_epoch: float) -> Path:
    """A spawn that fails the test: every refusal here comes before the fork."""
    raise AssertionError(f"a refusal was expected before this forked: {config} {start_epoch}")


def test_an_unheld_arm_refuses_before_anything_opens(free_locks: LockManager) -> None:
    """The operator has to have the arm in their hands before the handshake energizes it."""
    admission = session.admit(two_channels(), free_locks, acknowledged=False)

    assert not admission.ok
    assert any(session.HOLD_ACKNOWLEDGEMENT_FLAG in refusal for refusal in admission.refusals)


def test_the_run_command_refuses_and_forks_nothing_without_the_acknowledgement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The refusal is the entry point's, not a note in a docstring nobody runs."""
    monkeypatch.setattr(session, "list_can_channels", channel_lister(two_channels()))
    monkeypatch.setattr(session, "LockManager", lock_manager_factory(tmp_path))
    monkeypatch.setattr(session, "spawn_worker", _refuse_to_spawn)

    with redirect_stdout(io.StringIO()) as printed:
        code = session.main(_run_argv(tmp_path))

    assert code == session.EXIT_REFUSED
    assert session.HOLD_ACKNOWLEDGEMENT_FLAG in printed.getvalue()


def test_a_held_channel_lock_refuses_the_round(tmp_path: Path) -> None:
    """Two writers on one channel is the exclusivity SocketCAN RAW cannot provide (01 FR-SYS-005).

    The refusal names the holder, because "the lock is taken" leaves the operator with nothing to
    do about it.
    """
    holder = LockManager(lock_dir=str(tmp_path))
    assert holder.acquire_all([INTERFACE_A]).ok
    try:
        admission = session.admit(
            two_channels(), LockManager(lock_dir=str(tmp_path)), acknowledged=True
        )
    finally:
        holder.release_all()

    assert not admission.ok
    joined = " ".join(admission.refusals)
    assert INTERFACE_A in joined
    assert str(os.getpid()) in joined


def test_a_freed_channel_lock_admits_the_round(tmp_path: Path) -> None:
    """The lock refusal has to lift by itself, or the first held lock ends the procedure."""
    holder = LockManager(lock_dir=str(tmp_path))
    assert holder.acquire_all([INTERFACE_A]).ok
    holder.release_all()

    admission = session.admit(
        two_channels(), LockManager(lock_dir=str(tmp_path)), acknowledged=True
    )

    assert admission.ok, admission.refusals


def test_a_down_link_refuses_with_the_command_that_lifts_it(free_locks: LockManager) -> None:
    """The tool never escalates; it prints what the operator runs in their own shell."""
    admission = session.admit(two_channels(DOWN_STATE), free_locks, acknowledged=True)

    assert not admission.ok
    assert any("sudo ip link set" in refusal for refusal in admission.refusals)


def test_one_channel_is_nothing_to_tell_apart(free_locks: LockManager) -> None:
    """Identification over a single channel would resolve whatever moved, including a knock."""
    admission = session.admit((channel(INTERFACE_A, "0x0"),), free_locks, acknowledged=True)

    assert not admission.ok


def test_a_reading_with_a_silent_motor_is_refused_rather_than_used(
    motor_names: tuple[str, ...],
) -> None:
    """The bus answers a zeroed cache for a motor that never replied, and 0.0° looks plausible.

    Used, it makes the moved arm's delta collapse toward zero on that joint; refused, the
    operator is told which joint never answered.
    """
    bus = SilentMotorBus(motor_names, RESTING_ANGLE_DEG, silent=motor_names[0])
    reader = session.ChannelJointReader({INTERFACE_A: bus}, motor_names)

    with pytest.raises(session.ChannelReadError) as refusal:
        reader(INTERFACE_A)

    assert motor_names[0] in str(refusal.value)


def test_a_channel_that_was_never_opened_is_refused(motor_names: tuple[str, ...]) -> None:
    """A reader asked for a channel it holds no bus for must not answer a resting pose."""
    reader = session.ChannelJointReader(
        {INTERFACE_A: FakeChannelBus(motor_names, RESTING_ANGLE_DEG)}, motor_names
    )

    with pytest.raises(session.ChannelReadError):
        reader("can9")
