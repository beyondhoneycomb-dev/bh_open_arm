"""One read answers with the pose and the torque, and the caller gets both.

`ArmStateBoard` publishes a pose and a torque and states that pairing them is the point:
read separately they describe two different instants, and a residual computed across that
gap is a collision signal nobody can trust. Nothing could satisfy that promise while the
only read on the command path returned angles alone — the board's writer would have had to
either provoke a second bus round trip, on the one loop that keeps a brakeless arm up, or
fill the torque slot with a placeholder and claim a pairing it never had.

The vendor bus already answers with all three fields in one refresh cycle
(`DamiaoMotorsBus.sync_read_all_states`), so what is asserted here costs no extra traffic:
the torque was in the reply and was being dropped on the floor.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.calibration.schema import MOTOR_ORDER
from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower

# Deliberately not zero, and one value per joint rather than one repeated. A constant would
# pass against a torque vector built in the wrong order, and zero is what the bus's cache
# reports for a motor that never answered.
REST_POSE_DEG = 3.0

# The default build carries no motor on the gripper slot, so the frozen layout's last entry is
# widened rather than read. Both channels must widen the same slot: a torque that came back for
# a joint the pose call skipped would be a torque from a motor that was never addressed.
FITTED_TORQUE_NM = (0.5, -1.25, 2.0, -0.75, 1.5, -0.25, 3.5)
UNFITTED_SLOT_VALUE = 0.0

EXPECTED_TORQUE_NM = (*FITTED_TORQUE_NM, UNFITTED_SLOT_VALUE)
EXPECTED_POSE_DEG = (*(REST_POSE_DEG,) * len(FITTED_TORQUE_NM), UNFITTED_SLOT_VALUE)


@pytest.fixture
def follower(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> OaOpenArmFollower:
    """A fixture-bus arm whose fitted motors each report a distinct torque."""
    built = make_follower(position_deg=REST_POSE_DEG)
    built.bus.torque_nm = dict(zip(MOTOR_ORDER, FITTED_TORQUE_NM, strict=False))
    return built


def test_poll_reports_the_torque_the_bus_answered_with(follower) -> None:
    """The reply's torque reaches the caller, per joint, in the frozen layout's order."""
    _, torque, _ = follower._poll_states()

    assert tuple(torque) == EXPECTED_TORQUE_NM


def test_pose_and_torque_come_out_of_the_same_read(follower) -> None:
    """One round trip carries both, so the two describe one instant rather than two.

    Counting the reads is the assertion, not a performance note: a torque fetched by a second
    call would still produce the right numbers here while breaking the only property the pairing
    exists for.
    """
    angles, torque, _ = follower._poll_states()

    assert len(follower.bus.read_motors) == 1
    assert tuple(angles) == EXPECTED_POSE_DEG
    assert tuple(torque) == EXPECTED_TORQUE_NM
