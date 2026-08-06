"""Which motors get addressed, and where that set comes from.

`ARM_SEND_IDS` is the registration of a fully populated arm. The set on the bus is decided by the
fitted end effector, and addressing a motor that is not there is not a no-op: the frame goes out,
nobody ACKs it, the transmit error counter climbs, and the controller falls to ERROR-PASSIVE —
which degrades the seven joints that ARE present. A diagnostic that damages the thing it is
diagnosing is worse than no diagnostic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.can.rid.layout import ARM_SEND_IDS
from backend.endeffector import (
    ARM_JOINT_SEND_IDS,
    GRIPPER_SEND_ID,
    SIDE_LEFT,
    SIDE_RIGHT,
    RigEndEffectors,
    gripper_build,
    rig_path,
    spatula_build,
)
from scripts import can_node_watch as watch
from scripts.can_node_watch_tests.watch_doubles import (
    INTERFACE_A,
    INTERFACE_B,
    FakeNodeBus,
    arm_channel,
    channel,
    motors_for,
    target,
    two_channels,
    write_bench_records,
)


def test_the_registration_is_not_the_pollable_set() -> None:
    """The distinction this whole module rests on, pinned so it cannot quietly collapse."""
    assert GRIPPER_SEND_ID in ARM_SEND_IDS
    assert GRIPPER_SEND_ID not in spatula_build().motor_send_ids
    assert spatula_build().motor_send_ids == ARM_JOINT_SEND_IDS


def test_a_round_addresses_the_fitted_motors_and_nothing_else() -> None:
    """The spatula build has no motor on `0x08`, so no frame may carry that id."""
    arm = target(SIDE_LEFT, INTERFACE_A, spatula_build().motor_send_ids)
    bus = FakeNodeBus(motors_for(ARM_JOINT_SEND_IDS))

    watch.poll_round([arm_channel(arm, bus)], at_seconds=0.0)

    assert bus.sent_ids() == list(ARM_JOINT_SEND_IDS)
    assert GRIPPER_SEND_ID not in bus.sent_ids()


def test_a_gripper_build_adds_the_eighth_motor() -> None:
    """The set is read per arm, so a rig that really has a gripper watches it."""
    arm = target(SIDE_LEFT, INTERFACE_A, gripper_build().motor_send_ids)
    bus = FakeNodeBus(motors_for(gripper_build().motor_send_ids))

    watch.poll_round([arm_channel(arm, bus)], at_seconds=0.0)

    assert bus.sent_ids() == [*ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID]


def test_each_node_is_decoded_under_the_type_registered_at_its_id() -> None:
    """J1/J2 are DM8009, J3/J4 DM4340, J5-J8 DM4310 (`03` FR-MOT-001).

    The scaling is per type, so a watch that decoded every node as one type would report the
    wrong angle on five joints out of seven and never raise anything.
    """
    arm = watch.ArmWatch(target(SIDE_LEFT, INTERFACE_A, ARM_JOINT_SEND_IDS))

    types = {send_id: node.motor_type.value for send_id, node in arm.nodes.items()}

    assert types == {
        0x01: "DM8009",
        0x02: "DM8009",
        0x03: "DM4340",
        0x04: "DM4340",
        0x05: "DM4310",
        0x06: "DM4310",
        0x07: "DM4310",
    }


def test_the_targets_come_from_the_persisted_binding(tmp_path: Path) -> None:
    """Which arm is on which channel is read, never taken as an argument.

    Both arms answer on send `0x01–0x08` (`03` §2.1), so a bus scan cannot tell them apart and
    an interface name is not an identity — the adapter has already been seen at two USB paths.
    """
    channels = two_channels()
    write_bench_records(tmp_path, channels)

    targets = watch.arm_targets(tmp_path, channels)

    assert [(arm.side, arm.interface) for arm in targets] == [
        (SIDE_LEFT, INTERFACE_A),
        (SIDE_RIGHT, INTERFACE_B),
    ]
    assert all(arm.send_ids == ARM_JOINT_SEND_IDS for arm in targets)


def test_the_targets_carry_each_arms_own_fitted_set(tmp_path: Path) -> None:
    """One arm can carry a gripper and the other not; the record is per side."""
    channels = two_channels()
    write_bench_records(
        tmp_path,
        channels,
        RigEndEffectors(left=gripper_build(), right=spatula_build()),
    )

    targets = watch.arm_targets(tmp_path, channels)

    assert targets[0].send_ids == (*ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID)
    assert targets[1].send_ids == ARM_JOINT_SEND_IDS


def test_no_end_effector_record_falls_back_to_the_build_without_the_gripper(
    tmp_path: Path,
) -> None:
    """Defaulting the other way polls an id nobody answers on and degrades the whole controller.

    One default breaks the arm quietly; this one costs a refused gripper command and a message.
    """
    channels = two_channels()
    write_bench_records(tmp_path, channels)
    rig_path(tmp_path).unlink()

    targets = watch.arm_targets(tmp_path, channels)

    assert all(GRIPPER_SEND_ID not in arm.send_ids for arm in targets)


def test_a_bound_channel_that_is_not_present_refuses(tmp_path: Path) -> None:
    """The adapter moved ports, or a different one is plugged in — nothing to fall back to."""
    write_bench_records(tmp_path, two_channels())

    with pytest.raises(watch.WatchRefusedError) as refusal:
        watch.arm_targets(tmp_path, (channel(INTERFACE_A, "0x0"),))

    assert "follower_right" in str(refusal.value)


def test_no_binding_at_all_refuses(tmp_path: Path) -> None:
    """A watch that guessed an interface would report the left arm's nodes under the right name."""
    with pytest.raises(watch.WatchRefusedError):
        watch.arm_targets(tmp_path, two_channels())
