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

import pytest

from backend.actuation.clock import ManualClock
from backend.config.arm import ARM_BACKEND_DUMMY, ARM_BACKEND_NONE, ARM_BACKENDS, build_arm_session
from contracts.prim.schema import ARM_SIDES

# The eight-slot frozen layout: seven joints and the gripper slot.
JOINT_COUNT = 8


def test_the_default_backend_builds_no_session() -> None:
    """No arm named, no arm invented — the server serves REST and the bundle as it did."""
    assert build_arm_session(ARM_BACKEND_NONE, clock=ManualClock()) is None


def test_the_dummy_backend_builds_a_session_over_both_arms() -> None:
    """`FR-SIM-098` — the whole loop is exercisable with no bus, and a rig has two arms."""
    session = build_arm_session(ARM_BACKEND_DUMMY, clock=ManualClock())

    assert session is not None
    assert session.sides == ARM_SIDES


def test_a_dummy_tick_fills_every_slot_of_both_boards() -> None:
    """A board half-filled by an adapter is worse than an empty one: it reads as a measurement."""
    session = build_arm_session(ARM_BACKEND_DUMMY, clock=ManualClock())
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
    session = build_arm_session(ARM_BACKEND_DUMMY, clock=ManualClock())
    assert session is not None

    session.tick()

    left, right = (session.board(side).view().state for side in ARM_SIDES)
    assert left is not None
    assert right is not None
    assert left.joint_deg != right.joint_deg


def test_an_unknown_backend_names_the_ones_that_exist() -> None:
    """A typo must not fall through to "no arm", which looks exactly like the default."""
    with pytest.raises(ValueError, match=ARM_BACKEND_DUMMY):
        build_arm_session("realish", clock=ManualClock())


def test_the_backend_names_are_the_ones_the_cli_offers() -> None:
    """One list, so a name the parser accepts cannot be one the builder refuses."""
    assert ARM_BACKENDS == (ARM_BACKEND_NONE, ARM_BACKEND_DUMMY)
