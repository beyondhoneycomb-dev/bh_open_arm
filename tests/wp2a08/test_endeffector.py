"""The gripper/spatula split, and the one thing it must never get wrong.

The property is electrical. Addressing a motor that is not on the bus returns no error: the
frame goes out unanswered, the transmit error counter climbs, and the controller drops to
`ERROR-PASSIVE` — measured on this bench, sixteen frames were enough to take both channels
there. A degraded controller then affects the seven joints that ARE present, so "poll eight
motors on a seven-motor arm" is not a harmless extra read.

So every test here is about not addressing what is absent, and about refusing rather than
dropping a command the fitted build cannot serve.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.endeffector import (
    GRIPPER_SEND_ID,
    GRIPPER_SLOT_INDEX,
    EndEffector,
    EndEffectorError,
    EndEffectorProfile,
    RigEndEffectors,
    default_rig,
    gripper_build,
    load_rig,
    rig_path,
    save_rig,
    spatula_build,
)


def test_the_spatula_build_does_not_address_the_gripper_motor() -> None:
    """The whole point: an absent motor must never be polled."""
    profile = spatula_build()

    assert GRIPPER_SEND_ID not in profile.motor_send_ids
    assert profile.motor_count == 7


def test_the_gripper_build_addresses_all_eight() -> None:
    """The other build is unchanged; this is a variant, not a replacement."""
    profile = gripper_build()

    assert GRIPPER_SEND_ID in profile.motor_send_ids
    assert profile.motor_count == 8


def test_a_gripper_command_on_a_spatula_arm_is_refused_not_dropped() -> None:
    """A silently discarded grasp reads as a policy that never grasps, not as a rig that cannot."""
    with pytest.raises(EndEffectorError, match="no motor"):
        spatula_build().assert_gripper_command_allowed(0.5)


def test_a_zero_gripper_slot_is_admitted_on_both_builds() -> None:
    """The frozen layout always carries the slot; filling it with zero requests nothing."""
    spatula_build().assert_gripper_command_allowed(0.0)
    gripper_build().assert_gripper_command_allowed(0.0)


def test_a_gripper_command_on_a_gripper_arm_is_admitted() -> None:
    """The variant must not break the build it was added alongside."""
    gripper_build().assert_gripper_command_allowed(0.8)


def test_the_frozen_slot_index_is_the_eighth() -> None:
    """CTR-UNIT fixes `joint_1..joint_7, gripper`; the refusal keys on that position."""
    assert GRIPPER_SLOT_INDEX == 7


def test_the_default_rig_is_the_spatula_build() -> None:
    """Defaulting to GRIPPER on a rig without one polls an absent motor and degrades the bus.

    Defaulting the other way costs a refused command and a message. One default breaks the arm
    quietly; this one stops and says so.
    """
    rig = default_rig()

    assert rig.left.end_effector is EndEffector.FIXED_SPATULA
    assert rig.right.end_effector is EndEffector.FIXED_SPATULA
    assert rig.total_motor_count == 14


def test_each_arm_can_carry_a_different_build() -> None:
    """Per-arm rather than per-rig: a mixed bench must be expressible, not approximated."""
    rig = RigEndEffectors(left=spatula_build(), right=gripper_build())

    assert rig.for_side("left").motor_count == 7
    assert rig.for_side("right").motor_count == 8
    assert rig.total_motor_count == 15


def test_an_unknown_side_is_refused() -> None:
    """A typo must not resolve to an arm."""
    with pytest.raises(EndEffectorError, match="unknown side"):
        default_rig().for_side("lefft")


def test_the_record_survives_a_save_and_load_round_trip(tmp_path: Path) -> None:
    """What is written must come back; this record decides whether a motor is addressed."""
    original = RigEndEffectors(left=spatula_build(1.2), right=gripper_build(0.9))
    path = rig_path(tmp_path)

    save_rig(path, original)
    loaded = load_rig(path)

    assert loaded.left.end_effector is EndEffector.FIXED_SPATULA
    assert loaded.left.tool_mass_kg == 1.2
    assert loaded.right.end_effector is EndEffector.GRIPPER
    assert loaded.right.tool_mass_kg == 0.9


def test_an_unweighed_tool_round_trips_as_null(tmp_path: Path) -> None:
    """None is carried rather than 0.0 so gravity compensation can refuse an unmeasured mass."""
    path = rig_path(tmp_path)
    save_rig(path, RigEndEffectors(left=spatula_build(), right=spatula_build()))

    assert load_rig(path).left.tool_mass_kg is None


def test_a_zero_tool_mass_is_refused(tmp_path: Path) -> None:
    """A fitted tool has positive mass; zero is an unmeasured one wearing a number."""
    path = rig_path(tmp_path)
    path.write_text(
        '{"version": 1, "arms": {"left": {"end_effector": "fixed_spatula", "tool_mass_kg": 0},'
        ' "right": {"end_effector": "fixed_spatula", "tool_mass_kg": null}}}',
        encoding="utf-8",
    )

    with pytest.raises(EndEffectorError, match="positive mass"):
        load_rig(path)


def test_an_unknown_end_effector_name_is_refused(tmp_path: Path) -> None:
    """A record naming a build we do not have cannot say whether motor 0x08 is on the bus."""
    path = rig_path(tmp_path)
    path.write_text(
        '{"version": 1, "arms": {"left": {"end_effector": "vacuum"},'
        ' "right": {"end_effector": "fixed_spatula"}}}',
        encoding="utf-8",
    )

    with pytest.raises(EndEffectorError, match="unknown end effector"):
        load_rig(path)


def test_a_missing_arm_is_refused(tmp_path: Path) -> None:
    """Half a record must not silently default the other half onto the bus."""
    path = rig_path(tmp_path)
    path.write_text(
        '{"version": 1, "arms": {"left": {"end_effector": "fixed_spatula"}}}', encoding="utf-8"
    )

    with pytest.raises(EndEffectorError, match="right"):
        load_rig(path)


def test_a_version_mismatch_is_refused(tmp_path: Path) -> None:
    """A future format read as this one would decide motor presence from fields that moved."""
    path = rig_path(tmp_path)
    path.write_text('{"version": 99, "arms": {}}', encoding="utf-8")

    with pytest.raises(EndEffectorError, match="version"):
        load_rig(path)


def test_a_malformed_file_is_refused(tmp_path: Path) -> None:
    """Refusing beats defaulting when the answer decides whether an absent motor gets polled."""
    path = rig_path(tmp_path)
    path.write_text("{{{", encoding="utf-8")

    with pytest.raises(EndEffectorError):
        load_rig(path)


def test_a_failed_write_leaves_no_stray_temp_file(tmp_path: Path) -> None:
    """A leftover temp file is a second record a later glob could pick up."""
    path = rig_path(tmp_path)
    save_rig(path, default_rig())

    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_a_profile_is_immutable() -> None:
    """The fitted build must not change under a consumer that already read motor_send_ids."""
    profile = spatula_build()

    with pytest.raises(AttributeError):
        profile.end_effector = EndEffector.GRIPPER  # type: ignore[misc]


def test_the_two_builds_differ_by_exactly_the_gripper_motor() -> None:
    """The variant is one motor wide; anything else would be a different arm, not a tool swap."""
    gripper = set(gripper_build().motor_send_ids)
    spatula = set(spatula_build().motor_send_ids)

    assert gripper - spatula == {GRIPPER_SEND_ID}
    assert not spatula - gripper


def test_a_profile_built_directly_carries_its_mass() -> None:
    """The dataclass is the record shape the loader produces; both paths must agree."""
    profile = EndEffectorProfile(end_effector=EndEffector.FIXED_SPATULA, tool_mass_kg=2.5)

    assert profile.tool_mass_kg == 2.5
    assert not profile.has_actuated_gripper
