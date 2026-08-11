"""The `03` §2.8 gain registry: the five sets, what they cover, and what the gateway makes of them.

Two things are asserted here that a shape check would miss. The numbers are asserted as numbers —
a profile that kept its length and lost its elbow entry is still the wrong arm. And admissibility
is asserted by pushing every registered pair through the real gateway rather than by re-checking
`KP_MIN`/`KP_MAX` here, because a second copy of the bounds would agree with itself while the one
that runs disagreed.
"""

from __future__ import annotations

import pytest

from backend.actuation.gains import (
    CALIB_HOLD,
    COMPLIANT,
    GAIN_PROFILES,
    LEROBOT_FOLLOWER,
    LEROBOT_RUNTIME_PROFILE,
    ROS2_CONTROL_GRIPPER_KD,
    ROS2_CONTROL_GRIPPER_KP,
    STIFF,
    TELEOP_FOLLOWER,
    GainLineage,
    GainProfileError,
    NamedGainProfile,
    UnknownGainProfileError,
    profile_names,
    resolve_gain_profile,
)
from backend.actuation.guard import GuardSample
from backend.endeffector import GRIPPER_SEND_ID, spatula_build
from tests.wp103.conftest import degs, make_gateway, make_limits

# `03` §2.8, transcribed from the table rather than from another summary — the section says in as
# many words that a summary missing a set is the thing that is wrong, and these are the numbers the
# arm actually runs.
EXPECTED_KP = {
    COMPLIANT: (70.0, 70.0, 70.0, 60.0, 10.0, 10.0, 10.0, 10.0),
    STIFF: (230.0, 230.0, 190.0, 190.0, 30.0, 30.0, 30.0, 10.0),
    LEROBOT_FOLLOWER: (240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 25.0),
    TELEOP_FOLLOWER: (240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 16.0),
    CALIB_HOLD: (300.0, 300.0, 150.0, 150.0, 40.0, 40.0, 30.0),
}
EXPECTED_KD = {
    COMPLIANT: (2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5, 0.2),
    STIFF: (2.7, 2.7, 2.2, 2.2, 1.5, 1.5, 1.5, 0.2),
    LEROBOT_FOLLOWER: (5.0, 5.0, 3.0, 5.0, 0.3, 0.3, 0.3, 0.3),
    TELEOP_FOLLOWER: (3.0, 3.0, 3.0, 3.0, 0.2, 0.2, 0.2, 0.2),
    CALIB_HOLD: (2.5, 2.5, 2.5, 2.5, 0.8, 0.8, 0.8),
}

# The seven arm joints, and the two joints the shoulder-vs-elbow difference shows up on.
ARM_JOINT_COUNT = 7
WITH_GRIPPER_COUNT = 8
ELBOW_SEND_ID = 0x04
WRIST_SEND_ID = 0x07

# `compliant` at the elbow and at the wrist: the pair a single scalar cannot be (`03` §2.8).
COMPLIANT_ELBOW_KP = 60.0
COMPLIANT_WRIST_KP = 10.0

# A name nobody registered.
UNREGISTERED = "medium"


def _profiles() -> tuple[NamedGainProfile, ...]:
    """Every registered profile, so a new row is covered by these tests the moment it lands."""
    return tuple(GAIN_PROFILES[name] for name in profile_names())


def test_the_five_sets_are_registered() -> None:
    """`03` §2.8 registers five and says a summary that counts fewer is the thing that is wrong."""
    assert profile_names() == (COMPLIANT, STIFF, LEROBOT_FOLLOWER, TELEOP_FOLLOWER, CALIB_HOLD)


@pytest.mark.parametrize("name", tuple(EXPECTED_KP))
def test_each_profile_carries_the_spec_s_own_numbers(name: str) -> None:
    """The vectors are the values, not just the right shape.

    A length check passes on a profile whose elbow entry was copied from its neighbour, and that
    profile moves the arm.
    """
    profile = resolve_gain_profile(name)

    assert profile.kp == EXPECTED_KP[name]
    assert profile.kd == EXPECTED_KD[name]


@pytest.mark.parametrize("profile", _profiles(), ids=lambda profile: profile.name)
def test_every_registered_gain_is_admitted_by_the_gateway(profile: NamedGainProfile) -> None:
    """Every pair in every profile survives the check that runs before the wire (`03` FR-MOT-018).

    Each joint's pair is submitted on its own so a profile with one bad entry cannot hide behind
    seven good ones, and it goes through the gateway rather than a local bounds check: the encoder
    silently wraps an out-of-range gain, so the only bounds that matter are the ones the running
    filter applies.
    """
    gateway, _guard = make_gateway(make_limits())

    for kp, kd in zip(profile.kp, profile.kd, strict=True):
        result = gateway.submit(
            degs(1.0, 1.0),
            degs(0.0, 0.0),
            kp=(kp, kp),
            kd=(kd, kd),
            guard_sample=GuardSample.healthy(),
        )
        assert not result.rejected, f"{profile.name} kp={kp} kd={kd} was rejected: {result.reason}"


@pytest.mark.parametrize("profile", _profiles(), ids=lambda profile: profile.name)
def test_a_profile_is_per_joint_and_as_wide_as_its_source(profile: NamedGainProfile) -> None:
    """Seven entries or eight, kp and kd agreeing — never one number broadcast over the arm."""
    assert len(profile.kp) == len(profile.kd)
    assert len(profile.kp) in (ARM_JOINT_COUNT, WITH_GRIPPER_COUNT)


def test_calib_hold_covers_seven_joints_and_no_gripper() -> None:
    """Its source drives the arm as a seven-motor list and bumps the gripper separately.

    Padding an eighth entry on would invent a gain the calibration script never had, and dropping
    to a shared width would make `calib_hold` claim a gripper hold it does not define.
    """
    profile = resolve_gain_profile(CALIB_HOLD)

    assert not profile.covers_gripper
    assert profile.send_ids == (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07)
    with pytest.raises(GainProfileError, match="0x08"):
        profile.for_send_id(GRIPPER_SEND_ID)


def test_the_other_four_do_cover_the_gripper() -> None:
    """Their sources declare an eighth entry, and it stays theirs to offer."""
    for name in (COMPLIANT, STIFF, LEROBOT_FOLLOWER, TELEOP_FOLLOWER):
        assert resolve_gain_profile(name).covers_gripper


def test_the_gains_are_looked_up_by_joint_not_broadcast() -> None:
    """`compliant` is kp 60 at the elbow and kp 10 at the wrist — one scalar cannot be both."""
    profile = resolve_gain_profile(COMPLIANT)

    assert profile.for_send_id(ELBOW_SEND_ID).kp == COMPLIANT_ELBOW_KP
    assert profile.for_send_id(WRIST_SEND_ID).kp == COMPLIANT_WRIST_KP


def test_the_fitted_set_decides_how_many_entries_apply() -> None:
    """This rig is the spatula build: seven motors, no `0x08`, so the eighth entry is not applied.

    The gripper entry is left out because no fitted id asks for it, which is the visible version of
    the decision — not a silent truncation inside the profile.
    """
    fitted = spatula_build().motor_send_ids
    gains = resolve_gain_profile(COMPLIANT).for_send_ids(fitted)

    assert tuple(pair.send_id for pair in gains) == fitted
    assert len(gains) == ARM_JOINT_COUNT
    assert GRIPPER_SEND_ID not in tuple(pair.send_id for pair in gains)


def test_an_id_the_profile_does_not_cover_is_refused_rather_than_padded() -> None:
    """A fitted gripper against `calib_hold` is a question with no answer, and it is refused."""
    with pytest.raises(GainProfileError):
        resolve_gain_profile(CALIB_HOLD).for_send_ids((*spatula_build().motor_send_ids, 0x08))


def test_an_unknown_name_is_refused_and_never_defaulted() -> None:
    """`13` FR-GUI-068 forbids control starting with no profile: a substituted one is worse.

    The refusal names the registered ids, because the operator's next move is to pick one.
    """
    with pytest.raises(UnknownGainProfileError) as refusal:
        resolve_gain_profile(UNREGISTERED)

    assert COMPLIANT in str(refusal.value)
    assert STIFF in str(refusal.value)


def test_the_v1_era_sets_are_marked_non_canonical() -> None:
    """`03` FR-MOT-026: those two may only be offered with the label, so the label is a field."""
    assert resolve_gain_profile(LEROBOT_FOLLOWER).lineage is GainLineage.V1_DERIVED
    assert resolve_gain_profile(TELEOP_FOLLOWER).lineage is GainLineage.V1_ONLY
    assert not resolve_gain_profile(LEROBOT_FOLLOWER).is_canonical
    assert not resolve_gain_profile(TELEOP_FOLLOWER).is_canonical


def test_the_v2_sets_are_canonical() -> None:
    """`compliant` and `stiff` are the v2 canon D-4 settled on; `calib_hold` is the v2 tool's."""
    for name in (COMPLIANT, STIFF, CALIB_HOLD):
        assert resolve_gain_profile(name).is_canonical


def test_the_running_lerobot_profile_is_named_and_says_so() -> None:
    """The one profile LeRobot actually applies is a fact a caller meets on the profile itself."""
    assert LEROBOT_RUNTIME_PROFILE == LEROBOT_FOLLOWER
    assert "LeRobot" in resolve_gain_profile(LEROBOT_RUNTIME_PROFILE).role


@pytest.mark.parametrize("profile", _profiles(), ids=lambda profile: profile.name)
def test_every_profile_names_its_primary_source(profile: NamedGainProfile) -> None:
    """Provenance travels with the numbers, or the v1/v2 split is unanswerable at the call site."""
    assert profile.source.strip()


def test_the_ros2_control_gripper_pair_is_a_slot_and_not_a_profile_entry() -> None:
    """`03` §2.8 keeps it apart, and it belongs to a stack that is not our runtime.

    Three different numbers exist for one motor — this pair, `lerobot_follower`'s 25/0.3 that
    LeRobot actually sends, and `openarm_cell.yaml`'s kd 0.2 — so folding this one into a profile's
    gripper slot would put a ros2_control number on the wire under a profile's name.
    """
    assert (ROS2_CONTROL_GRIPPER_KP, ROS2_CONTROL_GRIPPER_KD) == (5.0, 0.1)
    for profile in _profiles():
        if not profile.covers_gripper:
            continue
        gripper = profile.for_send_id(GRIPPER_SEND_ID)
        assert (gripper.kp, gripper.kd) != (ROS2_CONTROL_GRIPPER_KP, ROS2_CONTROL_GRIPPER_KD)
