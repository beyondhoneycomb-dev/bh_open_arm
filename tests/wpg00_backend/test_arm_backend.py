"""Which arm `oa-serve` holds, and what a CAN-free one puts on the board.

`FR-SYS-003` makes the dummy↔real swap a config choice rather than a code edit, and this is the
host end of that choice: the server names a backend and gets an `ArmSession` or nothing. Nothing
is the default, because a process that invented an arm would put synthetic joint angles on the
board an operator reads and there would be no line anywhere saying so.

What the dummy backend is for is the wiring itself — the realtime channel, the stop path and the
board writer are all exercisable with no bus, which is the whole point of `FR-SIM-098`. What it
is not for is standing in for a reading. The startup report is where that distinction is charged
and `test_serve.py` is where the report is pinned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.actuation.clock import ManualClock
from backend.config.arm import (
    ARM_BACKEND_DUMMY,
    ARM_BACKEND_NONE,
    ARM_BACKEND_REAL,
    ARM_BACKENDS,
    ARM_BACKENDS_ON_HARDWARE,
    ArmChannelsUnavailableError,
    build_arm_backend,
    resolve_arm_channels,
)
from contracts.prim.schema import ARM_SIDES

# The eight-slot frozen layout: seven joints and the gripper slot.
JOINT_COUNT = 8


def test_the_default_backend_builds_no_session() -> None:
    """No arm named, no arm invented — the server serves REST and the bundle as it did."""
    assert build_arm_backend(ARM_BACKEND_NONE, clock=ManualClock()).session is None


def test_the_dummy_backend_builds_a_session_over_both_arms() -> None:
    """`FR-SIM-098` — the whole loop is exercisable with no bus, and a rig has two arms."""
    session = build_arm_backend(ARM_BACKEND_DUMMY, clock=ManualClock()).session

    assert session is not None
    assert session.sides == ARM_SIDES


def test_a_dummy_tick_fills_every_slot_of_both_boards() -> None:
    """A board half-filled by an adapter is worse than an empty one: it reads as a measurement."""
    session = build_arm_backend(ARM_BACKEND_DUMMY, clock=ManualClock()).session
    assert session is not None

    session.tick()

    for side in ARM_SIDES:
        state = session.board(side).view().state
        assert state is not None
        assert len(state.joint_deg) == JOINT_COUNT
        assert len(state.torque_nm) == JOINT_COUNT


def test_the_two_sides_are_read_one_after_the_other() -> None:
    """A bimanual rig has two buses, so the two arms are never read in the same instant.

    The dummy advances its synthetic step per poll, so the second side's pose differs from the
    first's. That is the honest shape rather than an artifact: `can0` and `can1` are read in
    sequence on the bench, and a double that answered both from one instant would let a caller
    assume a simultaneity the hardware does not offer.
    """
    session = build_arm_backend(ARM_BACKEND_DUMMY, clock=ManualClock()).session
    assert session is not None

    session.tick()

    left, right = (session.board(side).view().state for side in ARM_SIDES)
    assert left is not None
    assert right is not None
    assert left.joint_deg != right.joint_deg


def test_an_unknown_backend_names_the_ones_that_exist() -> None:
    """A typo must not fall through to "no arm", which looks exactly like the default."""
    with pytest.raises(ValueError, match=ARM_BACKEND_DUMMY):
        build_arm_backend("realish", clock=ManualClock())


def test_the_backend_names_are_the_ones_the_cli_offers() -> None:
    """One list, so a name the parser accepts cannot be one the builder refuses."""
    assert ARM_BACKENDS == (ARM_BACKEND_NONE, ARM_BACKEND_DUMMY, ARM_BACKEND_REAL)


def test_the_built_backend_hands_back_what_closing_it_takes() -> None:
    """A caller given only the session has nothing to close, and on hardware that is the bug.

    The real backend opens two CAN sockets and leaves fourteen motors enabled; a server that
    exited holding only an `ArmSession` would have no way to put either back. Pairing them is
    what makes the shutdown path the same shape for every name.
    """
    built = build_arm_backend(ARM_BACKEND_DUMMY, clock=ManualClock())

    built.close()

    assert built.session is not None


def test_closing_the_dummy_backend_disconnects_the_double() -> None:
    """The shutdown path is exercised by the name that needs no bus, or it is exercised nowhere.

    Nothing on the double is held open, so this frees nothing. It is asserted because a close
    only the hardware name reached would be a close nothing ever ran before an operator did.
    """
    built = build_arm_backend(ARM_BACKEND_DUMMY, clock=ManualClock())
    assert built.session is not None
    session = built.session

    built.close()

    with pytest.raises(RuntimeError):
        session.tick()


def test_closing_the_armless_backend_does_nothing_and_does_not_raise() -> None:
    """`--arm none` opened nothing, and its shutdown path runs on every exit all the same."""
    build_arm_backend(ARM_BACKEND_NONE, clock=ManualClock()).close()


def test_a_missing_channel_record_is_refused_rather_than_defaulted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The arms answer on the same CAN ids, so a default channel is a coin flip that looks sure.

    A fallback to "the first CAN interface" is indistinguishable from the right answer until the
    arm moves — and by then a left command has reached a right arm. The refusal names the tool
    that writes the record, because an operator who reads this has to know what to run.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    with pytest.raises(ArmChannelsUnavailableError, match="canbind_session"):
        resolve_arm_channels()


def test_the_hardware_names_do_not_include_the_double() -> None:
    """The startup report branches on this set, and the two lines it picks between are opposites.

    One says the readings are synthetic; the other says the motors are energized. A set that
    admitted the dummy would tell an operator with no bus to go support an arm, and a set that
    dropped the real name would tell an operator with fourteen live motors that nothing is real.
    """
    assert ARM_BACKEND_REAL in ARM_BACKENDS_ON_HARDWARE
    assert ARM_BACKEND_DUMMY not in ARM_BACKENDS_ON_HARDWARE
    assert ARM_BACKEND_NONE not in ARM_BACKENDS_ON_HARDWARE
