"""The board writer's read: one round trip, and the guard sample that read produced.

`ArmSession.tick` wants an `ArmFrame` per side and `get_observation` cannot supply one — it
answers a flat channel map, and the guard sample is not a channel. A writer built on it has to
invent a sample, and the only sample it can invent is a healthy one. That is honest over a
CAN-free double, where none of the four fields has anything to fail at, and it is a lie over
this class, where all four do. So the fabrication is what these tests are pointed at: every
assertion below is one a `GuardSample.healthy()` stand-in would fail.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.calibration.schema import MOTOR_ORDER
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BusReadRefusedError,
    OaOpenArmFollower,
)

# Deliberately not zero: zero is what the bus's cache reports for a motor that never answered,
# so a fixture resting there makes a real reading and a fabricated one the same tuple.
REST_POSE_DEG = 3.0

# One value per joint rather than one repeated — a constant passes against a torque vector
# assembled in the wrong order.
FITTED_TORQUE_NM = (0.5, -1.25, 2.0, -0.75, 1.5, -0.25, 3.5)

# The default build carries no motor on the gripper slot, so the frozen layout's last entry is
# widened rather than read.
UNFITTED_SLOT_VALUE = 0.0

EXPECTED_POSE_DEG = (*(REST_POSE_DEG,) * len(FITTED_TORQUE_NM), UNFITTED_SLOT_VALUE)
EXPECTED_TORQUE_NM = (*FITTED_TORQUE_NM, UNFITTED_SLOT_VALUE)

# A fitted motor to fail. The first is the one a build without a gripper still carries, so the
# case does not depend on the tool.
FAILING_MOTOR = MOTOR_ORDER[0]


@pytest.fixture
def follower(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> OaOpenArmFollower:
    """A zeroed fixture-bus arm whose fitted motors each report a distinct torque."""
    built = make_follower(position_deg=REST_POSE_DEG)
    built.bus.torque_nm = dict(zip(MOTOR_ORDER, FITTED_TORQUE_NM, strict=False))
    built.enable_drop_counting()
    return built


def test_the_frame_carries_the_pose_and_torque_the_bus_answered_with(follower) -> None:
    """Both channels in the frozen layout's order, widened at the slot with no motor behind it."""
    frame = follower.read_frame()

    assert tuple(reading.value for reading in frame.joint_deg) == EXPECTED_POSE_DEG
    assert tuple(reading.value for reading in frame.torque_nm) == EXPECTED_TORQUE_NM


def test_one_call_is_one_read(follower) -> None:
    """Counting reads is the assertion: this runs on the loop that keeps a brakeless arm up.

    A frame assembled from two round trips would produce these same numbers while breaking the
    one property pairing a pose with a torque exists for — that both describe one instant.
    """
    follower.read_frame()

    assert len(follower.bus.read_motors) == 1


def test_a_drop_reaches_the_frame_rather_than_being_reported_healthy(follower) -> None:
    """The sample is the read's own, not a constant — this is the fabrication check.

    A motor in `drop_motors` answers from its cache and the vendor logs the drop, so the values
    look exactly like a fresh reading and the record is the whole of the evidence. A writer that
    stamped `healthy()` would publish a stale pose onto the board with nothing marking it, and
    the deadman reads that field.
    """
    follower.bus.drop_motors = {FAILING_MOTOR}

    sample = follower.read_frame().guard

    assert sample.bus_read_ok is False


def test_a_clean_read_reports_the_bus_healthy(follower) -> None:
    """The other direction, so the check above cannot pass by reporting False unconditionally."""
    sample = follower.read_frame().guard

    assert sample.bus_read_ok is True
    assert sample.observation_present is True


def test_a_motor_that_never_answered_is_refused_rather_than_widened(follower) -> None:
    """The zeroed cache is the horizontal on an arm at the URDF zero, not a reading.

    Refused at the read rather than published: a board carrying that 0.0 is indistinguishable
    from a measurement, and a latch departing from it would leave as a move to the horizontal.
    """
    follower.bus.cache_only_motors = {FAILING_MOTOR}

    with pytest.raises(BusReadRefusedError, match=FAILING_MOTOR):
        follower.read_frame()
