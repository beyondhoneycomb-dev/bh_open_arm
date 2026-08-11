"""Everything that must hold before a socket opens, and what each refusal says.

The order matters and is asserted here: the bench record decides *which* channel the rest is
judged against, so a link or lock verdict over a channel this run would never open answers a
question nobody asked. Nothing in this file opens a channel or sends a frame.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.can.lock import LockManager
from backend.endeffector import GRIPPER_SEND_ID, RigEndEffectors, gripper_build, spatula_build
from contracts.units import Deg
from scripts.can_node_watch_tests.watch_doubles import (
    INTERFACE_A,
    channel,
    two_channels,
    write_bench_records,
)
from scripts.jog_joint import (
    KD_MAX,
    KP_MAX,
    MAX_DELTA_DEG,
    AbortLimits,
    JogRefusedError,
    channel_refusals,
    request_refusals,
    resolve_target,
)
from scripts.jog_joint_tests.jog_doubles import WRIST_SEND_ID, wrist_target

LEFT = "left"
RIGHT = "right"
DOWN_STATE = "STOPPED"

VALID_KP = 10.0
VALID_KD = 0.5
VALID_DELTA = Deg(5.0)
WRIST_LIMITS = AbortLimits(max_torque_nm=3.5, max_temp_c=80.0)

# A second channel key that is not the one the binding names, for the missing-channel case.
UNBOUND_DEV_ID = "0x9"


@pytest.fixture
def bench(tmp_path: Path) -> Path:
    """A config directory holding this rig's binding and end-effector records."""
    write_bench_records(tmp_path, two_channels())
    return tmp_path


def _refusals(**overrides: float) -> tuple[str, ...]:
    """Refusals for the wrist move, with named fields replaced one at a time."""
    return request_refusals(
        wrist_target(),
        Deg(overrides.get("delta", VALID_DELTA.value)),
        overrides.get("kp", VALID_KP),
        overrides.get("kd", VALID_KD),
        overrides.get("max_torque_nm", WRIST_LIMITS.max_torque_nm),
        overrides.get("max_temp_c", WRIST_LIMITS.max_temp_c),
    )


def test_a_fitted_arm_joint_resolves_to_the_channel_its_arm_is_bound_to(bench: Path) -> None:
    """The channel comes from the persisted binding, never from the interface name.

    Both arms answer on `0x01-0x08` (`03` §2.1), so a tool that picked a channel by name would
    move the other arm and report this one's id.
    """
    target = resolve_target(LEFT, WRIST_SEND_ID, bench, two_channels())

    assert target.interface == INTERFACE_A
    assert target.send_id == WRIST_SEND_ID


def test_the_two_arms_resolve_to_different_channels(bench: Path) -> None:
    """A binding that collapsed both arms onto one channel would move the wrong arm silently."""
    left = resolve_target(LEFT, WRIST_SEND_ID, bench, two_channels())
    right = resolve_target(RIGHT, WRIST_SEND_ID, bench, two_channels())

    assert left.interface != right.interface


def test_an_unfitted_motor_is_refused_before_anything_opens(bench: Path) -> None:
    """This rig is the spatula build: there is no motor on `0x08`.

    Addressing one that is not there is not a no-op. Nothing ACKs the frame, the transmit error
    counter climbs, and the controller drops to ERROR-PASSIVE — which degrades the seven joints
    that *are* on the bus.
    """
    with pytest.raises(JogRefusedError, match="ERROR-PASSIVE"):
        resolve_target(LEFT, GRIPPER_SEND_ID, bench, two_channels())


def test_a_fitted_gripper_is_still_refused_by_this_tool(tmp_path: Path) -> None:
    """Fitted is not the same as jog-able: the gripper is force-controlled, not position-commanded.

    It also has no URDF effort row, so there is nothing to derive an abort torque from — a jog
    with no torque ceiling is a jog with no property 3.
    """
    write_bench_records(
        tmp_path,
        two_channels(),
        RigEndEffectors(left=gripper_build(), right=spatula_build()),
    )

    with pytest.raises(JogRefusedError, match="POS_FORCE"):
        resolve_target(LEFT, GRIPPER_SEND_ID, tmp_path, two_channels())


def test_a_bench_with_no_records_is_refused(tmp_path: Path) -> None:
    """Which arm is on which channel cannot be read off the bus, so there is no fallback."""
    with pytest.raises(JogRefusedError):
        resolve_target(LEFT, WRIST_SEND_ID, tmp_path, two_channels())


def test_an_arm_whose_channel_is_gone_is_refused(bench: Path) -> None:
    """The adapter moved ports, or a different one is in. Guessing is what the binding forbids."""
    present = (channel(INTERFACE_A, UNBOUND_DEV_ID),)

    with pytest.raises(JogRefusedError, match="canbind_session"):
        resolve_target(LEFT, WRIST_SEND_ID, bench, present)


def test_a_delta_past_the_bound_is_refused() -> None:
    """The realistic mistake is a radian value in a degree field, or one extra digit."""
    refusals = _refusals(delta=MAX_DELTA_DEG + 1.0)

    assert len(refusals) == 1
    assert "--delta" in refusals[0]


def test_a_delta_at_the_bound_is_accepted() -> None:
    """A bound that refuses its own limit moves the limit, and nobody knows where it is."""
    assert _refusals(delta=MAX_DELTA_DEG) == ()
    assert _refusals(delta=-MAX_DELTA_DEG) == ()


def test_a_zero_delta_is_accepted() -> None:
    """Enable, hold where you are, disable. A legitimate first thing to ask of a joint."""
    assert _refusals(delta=0.0) == ()


def test_a_gain_outside_the_encoding_range_is_refused() -> None:
    """The encoder clamps an out-of-range gain silently (FR-MOT-018): refuse here or nowhere."""
    assert _refusals(kp=KP_MAX + 1.0)
    assert _refusals(kp=-1.0)
    assert _refusals(kd=KD_MAX + 1.0)


def test_a_zero_kd_is_refused() -> None:
    """Damiao's own constraint (FR-MOT-021): in position control kd = 0 makes the motor run away."""
    refusals = _refusals(kd=0.0)

    assert len(refusals) == 1
    assert "kd" in refusals[0]


def test_an_abort_torque_above_the_joint_limit_is_refused() -> None:
    """A ceiling above the joint's own effort limit never fires, which is not a ceiling."""
    refusals = _refusals(max_torque_nm=wrist_target().effort_limit_nm + 1.0)

    assert len(refusals) == 1
    assert "--max-torque" in refusals[0]


def test_an_abort_temperature_above_the_coil_fault_cap_is_refused() -> None:
    """Above the fault cap the motor protects itself first, and this check never runs."""
    refusals = _refusals(max_temp_c=200.0)

    assert len(refusals) == 1
    assert "--max-temp" in refusals[0]


def test_the_default_abort_torque_is_well_under_the_joint_limit() -> None:
    """The default has to sit above the joint's gravity hold and below its effort limit.

    Both halves matter. Too high and property 3 never fires; too low and it fires on a healthy
    arm — and an abort disables, which on a joint carrying weight is a fall.
    """
    target = wrist_target()

    assert 0.0 < target.default_abort_torque_nm < target.effort_limit_nm


def test_a_ready_channel_carries_no_refusal(tmp_path: Path) -> None:
    """The ordinary bench opens. A gate that refuses everything is not a gate."""
    assert channel_refusals(INTERFACE_A, two_channels(), LockManager(lock_dir=str(tmp_path))) == ()


def test_a_down_link_refuses_with_the_command_that_lifts_it(tmp_path: Path) -> None:
    """The tool never escalates; it prints what the operator runs in their own shell."""
    refusals = channel_refusals(
        INTERFACE_A, two_channels(DOWN_STATE), LockManager(lock_dir=str(tmp_path))
    )

    assert any("sudo ip link set" in refusal for refusal in refusals)


def test_an_absent_channel_refuses(tmp_path: Path) -> None:
    """The binding resolved to an interface the host no longer exposes."""
    refusals = channel_refusals(INTERFACE_A, (), LockManager(lock_dir=str(tmp_path)))

    assert len(refusals) == 1
    assert INTERFACE_A in refusals[0]


def test_a_held_channel_lock_refuses_the_move(tmp_path: Path) -> None:
    """Two writers on one channel is the exclusivity SocketCAN RAW cannot provide (01 FR-SYS-005).

    The refusal names the holder, because the operator's next move is to find out what that
    process is before taking a lock away from something that may be holding an arm up.
    """
    holder = LockManager(lock_dir=str(tmp_path))
    assert holder.acquire_all([INTERFACE_A]).ok
    try:
        refusals = channel_refusals(
            INTERFACE_A, two_channels(), LockManager(lock_dir=str(tmp_path))
        )
    finally:
        holder.release_all()

    assert len(refusals) == 1
    assert str(os.getpid()) in refusals[0]


def test_a_freed_channel_lock_admits_the_move(tmp_path: Path) -> None:
    """The lock refusal has to lift by itself, or the first held lock ends the tool."""
    holder = LockManager(lock_dir=str(tmp_path))
    assert holder.acquire_all([INTERFACE_A]).ok
    holder.release_all()

    assert channel_refusals(INTERFACE_A, two_channels(), LockManager(lock_dir=str(tmp_path))) == ()
