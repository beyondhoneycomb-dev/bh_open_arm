"""The collision guard is polled by the command path, and what it latches is a hold.

`send_action` is the only caller of `CollisionGuard.poll` on this path, so a poll it skips
leaves `_latched` unset and the WORKSPACE_COLLISION stage reading a `collision_latched` that
is False forever — a constant nothing downstream can tell from a healthy arm. Both directions
are pinned here: a drop reaches the guard, and a guard that never goes blind does not latch
anyway.

The two ways a motor fails to answer are separate cases and reach separate mechanisms. A motor
that has answered before leaves a real if stale angle in the bus's cache, so the read is usable
and the drop record is what latches the guard. A motor that has never answered leaves the zeroed
cache, and there is no usable pose at all — that one is refused at the read, because the pose a
latch holds at comes from the same read that failed, so a fabricated angle would make the stop a
move to it.

The direction of the failure is asserted, not assumed. This arm has no holding brake, so a
latch that cut torque would drop it; every latch here is checked to leave the hold gains
standing on the frame the accepted vector becomes.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.actuation.gateway import positions_to_batch
from backend.actuation.safety import SafetyReason
from backend.calibration.schema import MOTOR_ORDER
from contracts.units import Nm, Rad, deg_to_rad
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BusReadRefusedError,
    OaOpenArmFollower,
)

# A fitted motor to fail the readback on. Any of the seven arm joints does; the first is the
# one a build without a gripper still carries, so the case does not depend on the tool.
FAILING_MOTOR = MOTOR_ORDER[0]

# Several times the guard's residual debounce, so a residual channel wrongly reporting "over
# threshold" cannot stay under the debounce and pass this by accident.
HEALTHY_COMMAND_COUNT = 10

# Deliberately not zero. Zero is what the bus's cache reports for a motor that never answered,
# so a fixture resting there makes a hold at the measured pose and a hold at a fabricated one
# the same tuple, and every assertion drawn between them passes without checking anything.
# Small enough to sit inside every URDF joint limit.
REST_POSE_DEG = 3.0


def _send(follower: OaOpenArmFollower) -> None:
    """Command the arm to stay where it is — the smallest command that still runs the gate."""
    follower.send_action({f"{motor}.pos": REST_POSE_DEG for motor in MOTOR_ORDER})


@pytest.fixture
def follower(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> OaOpenArmFollower:
    """A zeroed fixture-bus arm whose bus has answered every read so far."""
    return make_follower(position_deg=REST_POSE_DEG)


def test_a_motor_that_never_answered_is_refused_rather_than_read_as_zero(follower) -> None:
    """The bus's zeroed cache is not a pose, and substituting it makes a stop into a move.

    `sync_read_all_states` returns an entry for every motor it was asked about, so a motor that
    has never answered arrives as the cache the bus was built with — position 0.0, which on an
    arm hanging at the URDF zero is the horizontal. Nothing downstream can tell that from a
    measurement, and the same silence latches the guard, whose hold departs from this very
    vector. So the read is refused here and no command is submitted at all.
    """
    follower.bus.cache_only_motors = {FAILING_MOTOR}

    with pytest.raises(BusReadRefusedError, match=FAILING_MOTOR):
        _send(follower)

    assert follower.last_gate_result is None
    assert follower.gateway.frames == ()


def test_a_reply_short_of_a_fitted_motor_is_refused_the_same_way(follower) -> None:
    """A missing key and the zeroed cache are one case: no answer for a motor that is fitted.

    The real bus never returns a short reply, so this is the shape a fixture can produce and the
    bench cannot. It is refused rather than widened for the same reason — the widening default
    is 0.0 deg, and a default that only appears when something is wrong is the worst possible
    time for it to look like a measurement.
    """
    follower.bus.omit_motors = {FAILING_MOTOR}

    with pytest.raises(BusReadRefusedError, match=FAILING_MOTOR):
        _send(follower)

    assert follower.last_gate_result is None


def test_the_latched_command_is_recorded_once_and_accepted_as_the_present_pose(follower) -> None:
    """A latch is a rejection, and a rejection still records both audit channels."""
    follower.connect_readonly()
    follower.bus.drop_motors = {FAILING_MOTOR}

    _send(follower)

    frames = follower.gateway.frames
    assert len(frames) == 1
    result = follower.last_gate_result
    assert result is not None
    assert frames[0].accepted == result.accepted


def test_a_latch_holds_the_arm_under_power_rather_than_dropping_torque(follower) -> None:
    """The latch must produce a Cat-2 hold: same pose, no torque, hold gains still standing.

    This arm has no mechanical brake. Zeroing the feed-forward torque is not the same act as
    disabling torque, and the two are indistinguishable from the returned action alone — so
    the emitted MIT frame's stiffness is checked, and the bus double's torque-drop counter.

    The held angle is checked against the pose the bus reported rather than against zero: a
    hold that had fabricated its vector would also be a tuple of equal values, and only a
    non-zero reading tells the two apart.
    """
    follower.connect_readonly()
    follower.bus.drop_motors = {FAILING_MOTOR}

    _send(follower)

    result = follower.last_gate_result
    assert result is not None
    assert result.accepted == tuple(follower.gateway.frames[0].accepted)
    assert result.feedforward_torque_nm == tuple(Nm(0.0) for _ in MOTOR_ORDER)
    assert follower.bus.disable_calls == 0

    emitted = positions_to_batch(tuple(deg_to_rad(angle) for angle in result.accepted))
    # Positive stiffness and positive damping, stated as the property rather than against the
    # constants the frame was built from: `kp == MIT_HOLD_KP` compares a value to itself and
    # stays green with the hold gains set to zero, which is the arm going limp.
    assert all(command.kp > 0.0 for command in emitted)
    assert all(command.kd > 0.0 for command in emitted)
    assert all(command.tau == Nm(0.0) for command in emitted)
    held = deg_to_rad(follower.gateway.frames[0].accepted[0])
    assert held != Rad(0.0)
    assert emitted[0].q == held


def test_a_packet_drop_during_the_read_latches_as_a_failed_bus_read(follower) -> None:
    """A motor that did not answer is a distinct cause from a reply that came back short.

    `sync_read_all_states` hands back a cache entry for a motor that never answered, so the
    returned mapping is complete either way and the vendor's drop record is the only evidence
    the frame was missing. The counter has to be attached by the bring-up for that to be true.
    """
    follower.connect_readonly()
    follower.bus.drop_motors = {FAILING_MOTOR}

    _send(follower)

    result = follower.last_gate_result
    assert result is not None
    assert result.reason is SafetyReason.COLLISION_LATCH
    assert follower.last_latch_reason is not None
    assert follower.last_latch_reason.gate_id == "COLLISION_GUARD:bus_read_failed"


def test_a_healthy_arm_is_never_latched_however_long_it_is_commanded(follower) -> None:
    """The regression that matters most: an uncalibrated detector is not a blind guard.

    Residual detection is not armed on this host, and the honest report of an unarmed
    detector is "nothing crossed the threshold". Reporting it as blindness instead would
    latch here on the third command and leave no way back.
    """
    follower.connect_readonly()

    for _ in range(HEALTHY_COMMAND_COUNT):
        _send(follower)

    assert not follower.gateway.guard.is_latched
    assert follower.last_latch_reason is None
    result = follower.last_gate_result
    assert result is not None
    assert result.reason is not SafetyReason.COLLISION_LATCH
    assert not result.rejected


def test_a_healthy_arm_with_no_lock_manager_is_not_treated_as_having_lost_its_lock(
    follower,
) -> None:
    """A session that never claimed a CAN lock has not lost one.

    The follower's lock manager is optional and the fixture path has none. Reading that
    absence as a lock timeout would latch every manager-less caller on its first command.
    """
    _send(follower)

    assert not follower.gateway.guard.is_latched


def test_a_gripperless_build_is_not_latched_for_the_slot_it_does_not_carry(
    make_follower,
    calibrated: None,
) -> None:
    """The observation check names the fitted motors, not the frozen eight-slot layout.

    `MOTOR_ORDER` is the contract, not an inventory. Checking the readback against all eight
    would report every gripperless arm as blind on its first command.
    """
    arm = make_follower(position_deg=REST_POSE_DEG)
    assert len(arm._fitted_motors()) < len(MOTOR_ORDER)

    _send(arm)

    assert not arm.gateway.guard.is_latched


def test_an_operator_ack_releases_the_latch_and_the_next_command_is_admitted(follower) -> None:
    """A fail-closed latch needs an exit, or one dropped reply ends the session.

    Nothing in the tick path clears it — that is the contract — so the ack is checked to be
    the thing that does, and to be inert until the underlying fault is gone.
    """
    follower.connect_readonly()
    follower.bus.drop_motors = {FAILING_MOTOR}
    _send(follower)
    assert follower.gateway.guard.is_latched

    follower.acknowledge_collision_latch()
    assert not follower.gateway.guard.is_latched
    assert follower.last_latch_reason is None

    follower.bus.drop_motors = set()
    _send(follower)

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected


def test_an_ack_with_the_bus_still_blind_latches_again_on_the_next_command(follower) -> None:
    """The ack clears the latch, not the fault: a still-blind read latches on the next poll."""
    follower.connect_readonly()
    follower.bus.drop_motors = {FAILING_MOTOR}
    _send(follower)
    follower.acknowledge_collision_latch()

    _send(follower)

    assert follower.gateway.guard.is_latched
    result = follower.last_gate_result
    assert result is not None
    assert result.reason is SafetyReason.COLLISION_LATCH
