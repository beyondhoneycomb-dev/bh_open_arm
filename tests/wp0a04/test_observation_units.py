"""Every index of the flattened observation.state carries a unit tag (WP-0A-04).

Acceptance item 7 / `16` D-8: the bimanual observation vector mixes deg, deg/s and
Nm in one array, and normalisation statistics can only be split by channel group if
each index's unit is known. An untagged index is the failure this guards against.
"""

from __future__ import annotations

from contracts.units import Deg, DegPerSec, Nm, expected_dim, observation_state_units


def test_bimanual_vector_is_48_dimensional() -> None:
    """The bimanual layout is 48 = 2 arms x 8 motors x 3 channels (`10` §2.3)."""
    channels = observation_state_units(bimanual=True)
    assert len(channels) == 48 == expected_dim(bimanual=True)


def test_single_arm_vector_is_24_dimensional() -> None:
    """The single-arm layout is 24 = 8 motors x 3 channels."""
    channels = observation_state_units(bimanual=False)
    assert len(channels) == 24 == expected_dim(bimanual=False)


def test_every_index_carries_a_unit_tag() -> None:
    """No index is untagged; each unit is one of the frozen tag types."""
    for channel in observation_state_units(bimanual=True):
        assert channel.unit in (Deg, DegPerSec, Nm), channel


def test_indices_are_contiguous_and_ordered() -> None:
    """Indices run 0..47 in declaration order, so `names` stays index-aligned."""
    channels = observation_state_units(bimanual=True)
    assert [channel.index for channel in channels] == list(range(48))


def test_channel_units_follow_pos_vel_torque() -> None:
    """Within a motor the order is pos(deg), vel(deg/s), torque(Nm)."""
    channels = observation_state_units(bimanual=True)
    assert (channels[0].suffix, channels[0].unit) == ("pos", Deg)
    assert (channels[1].suffix, channels[1].unit) == ("vel", DegPerSec)
    assert (channels[2].suffix, channels[2].unit) == ("torque", Nm)


def test_layout_is_arm_major() -> None:
    """The first 24 indices are the left arm, the next 24 the right arm."""
    channels = observation_state_units(bimanual=True)
    assert channels[0].name == "left_joint_1.pos"
    assert channels[23].name == "left_gripper.torque"
    assert channels[24].name == "right_joint_1.pos"
    assert channels[47].name == "right_gripper.torque"
