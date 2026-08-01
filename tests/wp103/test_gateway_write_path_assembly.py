"""The single writer emits only what the eight-check filter passed.

The gateway and the `ActuationScheduler` are verified apart elsewhere. What is verified here
is the join: `send_action`'s accepted output is what reaches the mailbox, so the frame the one
CAN writer sends is a frame the filter admitted or held.

The discriminating input is an unsafe *rate*. A 30° step is inside every joint's mechanical
envelope, so the decider's position clamp passes it through untouched and the arm is commanded
27° away inside one 20 ms period. Only the ordered filter refuses that, which is why a target
published around the filter is not merely unaudited but unsafe.

The two arms sit at different present angles throughout. With both halves at one angle a
bimanual vector assembled in the wrong arm order reads exactly like a correct one, and the
emitted frame would not show the difference.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import yaml

from backend.actuation import (
    AcceptedTargetPublisher,
    Emission,
    EmissionLabel,
    FaultInjectionHarness,
    GateResult,
    ManualClock,
    ReasonCode,
    SafetyReason,
    TargetMailbox,
    TimestampedTarget,
)
from backend.actuation.config import FRESHNESS_WINDOW_SEC
from backend.actuation.safety import POSITION_CONTROL_KD_FLOOR
from backend.calibration.schema import MOTOR_ORDER
from backend.torque_bringup import assert_safe_hold
from contracts.action import CONTRACT_PATH, ExecutedMitCommand
from contracts.units import Deg, deg_to_rad
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    SIDE_PREFIXES,
    BiOaOpenArmFollower,
    OaOpenArmFollower,
)

# Present angles, one per arm. Distinct so the arm-major placement of each half is visible.
LEFT_PRESENT_DEG = 3.0
RIGHT_PRESENT_DEG = 7.0

# A commanded angle no rate guard admits: 27° away from present in one 20 ms control period is
# 23 rad/s against a 1.57 rad/s shoulder ceiling, while staying inside every mechanical joint
# limit. The filter stops it; a position clamp does not.
UNSAFE_RATE_DEG = 30.0

# A step every guard admits: 1° in one control period is 0.87 rad/s, under the same ceiling.
ADMITTED_STEP_DEG = 1.0
LEFT_ADMITTED_DEG = LEFT_PRESENT_DEG + ADMITTED_STEP_DEG
RIGHT_ADMITTED_DEG = RIGHT_PRESENT_DEG + ADMITTED_STEP_DEG

# A wrist feed-forward torque inside the URDF effort band, so the request itself is admissible
# and only the filter's verdict decides whether it survives to the frame.
WRIST_MOTOR = MOTOR_ORDER[4]
WRIST_TORQUE_NM = 5.0

# What the gripper slot reports on a build with no motor on 0x08: the read names the fitted
# motors, so the slot is widened back to the frozen layout with this rather than with an answer
# from a motor that is not on the bus.
UNREAD_SLOT_DEG = 0.0

# What a held frame carries on every joint: no feed-forward torque, no commanded motion.
HELD_TORQUE_NM = 0.0
HELD_VELOCITY_RAD_S = 0.0

# Agreement tolerance for a degree-to-radian round trip.
ANGLE_TOLERANCE_RAD = 1e-9

# How far the clock is pushed to break the action stream: two freshness windows, so the gap is
# unambiguously past the bound rather than sitting on it.
STREAM_BREAK_SEC = FRESHNESS_WINDOW_SEC * 2.0


class CountingMailbox(TargetMailbox):
    """A real mailbox that also counts slot swaps.

    The count is what makes "one swap per bimanual command" observable; a pair that published
    each arm's half separately would show two.
    """

    def __init__(self) -> None:
        """Create an empty mailbox with no swaps recorded."""
        super().__init__()
        self.publish_count = 0

    def publish(self, target: TimestampedTarget) -> None:
        """Count the swap and perform it."""
        self.publish_count += 1
        super().publish(target)


def arm_move(target_deg: float) -> dict[str, float]:
    """Build a single-arm position action commanding every joint to one angle.

    Args:
        target_deg: The commanded angle for every joint.

    Returns:
        (dict[str, float]) The action, keys `{motor}.pos`.
    """
    return {f"{motor}.pos": target_deg for motor in MOTOR_ORDER}


def bimanual_move(left_deg: float, right_deg: float) -> dict[str, float]:
    """Build a bimanual position action commanding each arm's joints to one angle.

    Args:
        left_deg: The commanded angle for every left-arm joint.
        right_deg: The commanded angle for every right-arm joint.

    Returns:
        (dict[str, float]) The action, keys `{side}_{motor}.pos`.
    """
    left, right = SIDE_PREFIXES
    return {
        **{f"{left}_{motor}.pos": left_deg for motor in MOTOR_ORDER},
        **{f"{right}_{motor}.pos": right_deg for motor in MOTOR_ORDER},
    }


def emitted_angles_rad(batch: tuple[ExecutedMitCommand, ...]) -> tuple[float, ...]:
    """Return the commanded angle of every joint in an emitted MIT batch, radians.

    Args:
        batch: The frame the single writer sent.

    Returns:
        (tuple[float, ...]) One angle per bimanual joint.
    """
    return tuple(command.q.value for command in batch)


def bimanual_pose_rad(left_deg: float, right_deg: float) -> tuple[float, ...]:
    """Build the arm-major bimanual angle vector for two per-arm angles, radians.

    The gripper slot carries `UNREAD_SLOT_DEG` rather than the arm's angle. The present-pose read
    names the motors the fitted tool carries, and on the default build that is seven — nothing
    answers on `0x08`, so a poll of it is an unanswered frame that walks the controller toward
    ERROR-PASSIVE. The slot is still in the frozen layout and still commanded, and the value it
    reports is the width-widening default rather than a reading of a motor that is not there.

    Args:
        left_deg: The angle every fitted left-arm joint reports.
        right_deg: The angle every fitted right-arm joint reports.

    Returns:
        (tuple[float, ...]) The sixteen angles, left arm first.
    """
    fitted = len(MOTOR_ORDER) - 1
    per_arm = [[angle] * fitted + [UNREAD_SLOT_DEG] for angle in (left_deg, right_deg)]
    return tuple(deg_to_rad(Deg(degrees)).value for arm in per_arm for degrees in arm)


def assembled_pair(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
) -> tuple[BiOaOpenArmFollower, FaultInjectionHarness]:
    """Stand up a pair whose accepted output feeds a live scheduler's mailbox.

    The harness owns the scheduler, its fake bus and the clock. The arms measure their
    action-stream gap on that same clock and publish stamped with it, so the age the gateway
    judges and the age the tick judges are readings of one time base.

    Args:
        make_bimanual: The bimanual follower factory.

    Returns:
        (tuple[BiOaOpenArmFollower, FaultInjectionHarness]) The wired pair and its spine.
    """
    harness = FaultInjectionHarness()
    publisher = AcceptedTargetPublisher(harness.mailbox, harness.clock, SIDE_PREFIXES)
    pair = make_bimanual(
        position_deg=LEFT_PRESENT_DEG,
        right_position_deg=RIGHT_PRESENT_DEG,
        clock=harness.clock,
        publisher=publisher,
    )
    return pair, harness


def tick_with_live_deadman(harness: FaultInjectionHarness) -> Emission:
    """Run one tick with the deadman renewed, so the mailbox alone decides the emission.

    An unrenewed lease lapses into its own hold, which would mask what the published target
    did or did not carry.

    Args:
        harness: The spine to tick.

    Returns:
        (Emission) The emission that tick produced.
    """
    harness.renew()
    return harness.tick()


def a_real_decision(make_follower: Callable[..., OaOpenArmFollower]) -> GateResult:
    """Return a gateway decision produced by a real command on a publisher-less arm.

    Args:
        make_follower: The single-arm follower factory.

    Returns:
        (GateResult) The verdict the arm's own gateway reached.
    """
    arm = make_follower(position_deg=LEFT_PRESENT_DEG)
    arm.send_action(arm_move(LEFT_ADMITTED_DEG))
    decision = arm.last_gate_result
    assert decision is not None
    return decision


def test_send_action_accepted_output_reaches_the_single_writer(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """An unsafe-rate target reaches the writer as the present-pose hold, never as itself."""
    pair, harness = assembled_pair(make_bimanual)

    pair.send_action(bimanual_move(UNSAFE_RATE_DEG, UNSAFE_RATE_DEG))
    emission = tick_with_live_deadman(harness)

    left = pair.left_arm.last_gate_result
    right = pair.right_arm.last_gate_result
    assert left is not None
    assert right is not None
    # Stopped on a rate check — not on the zero check, and not merely position-clamped.
    assert left.rejected
    assert right.rejected
    assert left.reason in {SafetyReason.VELOCITY_LIMIT, SafetyReason.STEP_DELTA}
    # What the writer sent is each arm's present pose, not the 30° that was asked for.
    assert emission.label is EmissionLabel.ACCEPTED_TARGET
    assert emitted_angles_rad(emission.batch) == pytest.approx(
        bimanual_pose_rad(LEFT_PRESENT_DEG, RIGHT_PRESENT_DEG), abs=ANGLE_TOLERANCE_RAD
    )
    requested_rad = deg_to_rad(Deg(UNSAFE_RATE_DEG)).value
    assert all(
        abs(angle - requested_rad) > ANGLE_TOLERANCE_RAD
        for angle in emitted_angles_rad(emission.batch)
    )


def test_the_frame_a_refusal_produces_is_a_powered_hold(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """The refused command becomes a powered hold, with no torque left standing.

    On an arm with no mechanical brake the difference between a hold and a drop is kp: a frame
    at kp=0 commands no restoring torque and the arm falls. That rule has one definition
    (`assert_safe_hold`) and this reuses it rather than restating the bound — comparing the
    emitted gain against the constant that produced it would pass however low the constant
    went. The wrist torque is in band on the way in, so a frame that still carried it would be
    a push nobody's accepted command asked for.
    """
    pair, harness = assembled_pair(make_bimanual)
    left_side = SIDE_PREFIXES[0]

    pair.send_action(
        bimanual_move(UNSAFE_RATE_DEG, UNSAFE_RATE_DEG),
        feedforward_torque_nm={f"{left_side}_{WRIST_MOTOR}": WRIST_TORQUE_NM},
    )
    emission = tick_with_live_deadman(harness)

    assert_safe_hold(emission.batch)
    for command in emission.batch:
        assert command.kd > POSITION_CONTROL_KD_FLOOR
        assert command.dq.value == HELD_VELOCITY_RAD_S
        assert command.tau.value == HELD_TORQUE_NM


def test_the_mailbox_carries_the_accepted_vector_not_the_request(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """The slot the scheduler reads holds the filter's verdict, before any tick runs."""
    pair, harness = assembled_pair(make_bimanual)

    pair.send_action(bimanual_move(UNSAFE_RATE_DEG, UNSAFE_RATE_DEG))

    published = harness.mailbox.take_latest()
    assert published is not None
    fitted = len(MOTOR_ORDER) - 1
    held = (
        (LEFT_PRESENT_DEG,) * fitted
        + (UNREAD_SLOT_DEG,)
        + (RIGHT_PRESENT_DEG,) * fitted
        + (UNREAD_SLOT_DEG,)
    )
    assert tuple(angle.value for angle in published.request.values) == pytest.approx(held)
    assert all(angle.value != UNSAFE_RATE_DEG for angle in published.request.values)


def test_an_admitted_target_reaches_the_writer_as_the_accepted_angle(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """A command the filter admits moves the arm — the join is not a permanent hold.

    Without this, an assembly that published the present pose unconditionally would satisfy
    every refusal test in this file while commanding nothing, ever.
    """
    pair, harness = assembled_pair(make_bimanual)

    pair.send_action(bimanual_move(LEFT_ADMITTED_DEG, RIGHT_ADMITTED_DEG))
    emission = tick_with_live_deadman(harness)

    left = pair.left_arm.last_gate_result
    right = pair.right_arm.last_gate_result
    assert left is not None
    assert right is not None
    assert not left.rejected
    assert not right.rejected
    accepted_rad = tuple(
        deg_to_rad(angle).value for angle in tuple(left.accepted) + tuple(right.accepted)
    )
    assert emitted_angles_rad(emission.batch) == pytest.approx(
        accepted_rad, abs=ANGLE_TOLERANCE_RAD
    )
    # And it did move: the left shoulder is at the commanded angle, not where it started.
    assert emission.batch[0].q.value == pytest.approx(
        deg_to_rad(Deg(LEFT_ADMITTED_DEG)).value, abs=ANGLE_TOLERANCE_RAD
    )


def test_a_broken_action_stream_reaches_the_writer_as_the_present_pose(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """The gap the watchdog measures is the age the filter judges on this path.

    The second command is identical to the first, which was admitted, so the only thing that
    can hold it is the measured silence between them. A path handing the gateway a fresh zero
    would command the move again.
    """
    pair, harness = assembled_pair(make_bimanual)
    pair.send_action(bimanual_move(LEFT_ADMITTED_DEG, RIGHT_ADMITTED_DEG))
    tick_with_live_deadman(harness)

    harness.clock.advance(STREAM_BREAK_SEC)
    pair.send_action(bimanual_move(LEFT_ADMITTED_DEG, RIGHT_ADMITTED_DEG))
    emission = tick_with_live_deadman(harness)

    left = pair.left_arm.last_gate_result
    assert left is not None
    assert left.reason is SafetyReason.STALE_SOURCE
    # Held at the pose the arms report — not cut, and not moved to the commanded angle.
    assert emitted_angles_rad(emission.batch) == pytest.approx(
        bimanual_pose_rad(LEFT_PRESENT_DEG, RIGHT_PRESENT_DEG), abs=ANGLE_TOLERANCE_RAD
    )


def test_one_arm_commanded_alone_publishes_nothing(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """A round missing a side never reaches the mailbox, so no half is invented.

    The bimanual frame is sixteen joints wide. Publishing one arm's eight and filling the rest
    from whatever was in the slot commands the other arm to a pose no decision produced.
    """
    pair, harness = assembled_pair(make_bimanual)

    pair.left_arm.send_action(arm_move(LEFT_ADMITTED_DEG))

    assert harness.mailbox.take_latest() is None
    emission = tick_with_live_deadman(harness)
    assert emission.label is EmissionLabel.STALE_SOURCE_HOLD
    assert emission.reason is ReasonCode.MAILBOX_EMPTY


def test_one_bimanual_command_swaps_the_slot_once(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """Both halves land in one swap; a per-arm publish would show as two."""
    mailbox = CountingMailbox()
    clock = ManualClock()
    publisher = AcceptedTargetPublisher(mailbox, clock, SIDE_PREFIXES)
    pair = make_bimanual(
        position_deg=LEFT_PRESENT_DEG,
        right_position_deg=RIGHT_PRESENT_DEG,
        clock=clock,
        publisher=publisher,
    )

    pair.send_action(bimanual_move(LEFT_ADMITTED_DEG, RIGHT_ADMITTED_DEG))

    assert mailbox.publish_count == 1


def test_an_arm_with_no_publisher_reaches_no_writer(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """An arm built outside a torque-ON session filters, answers, and commands nothing.

    Stated rather than left to be discovered: an absent publisher is the difference between a
    wired robot and a follower that only answers questions.
    """
    harness = FaultInjectionHarness()
    follower = make_follower(position_deg=LEFT_PRESENT_DEG, clock=harness.clock)

    applied = follower.send_action(arm_move(LEFT_ADMITTED_DEG))

    assert applied[f"{MOTOR_ORDER[0]}.pos"] == pytest.approx(LEFT_ADMITTED_DEG)
    assert harness.mailbox.take_latest() is None


def test_a_side_the_publisher_never_declared_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """An undeclared side would count toward a round that a declared arm is still missing from.

    A round completes on a count of buffered decisions, and the count cannot see whose they
    are; refusing the name is what keeps it from reading two as both arms.
    """
    publisher = AcceptedTargetPublisher(TargetMailbox(), ManualClock(), SIDE_PREFIXES)
    decision = a_real_decision(make_follower)

    with pytest.raises(ValueError, match="not one of the declared arms"):
        publisher.offer("middle", decision)


def test_a_repeated_side_is_refused_at_construction() -> None:
    """Declaring one side twice buffers one decision against two slots — no round completes.

    The pair would then publish nothing for as long as it ran, and an arm commanded into
    silence is indistinguishable from an arm holding on purpose.
    """
    left = SIDE_PREFIXES[0]

    with pytest.raises(ValueError, match="repeat a name"):
        AcceptedTargetPublisher(TargetMailbox(), ManualClock(), (left, left))


def test_no_declared_sides_is_refused_at_construction() -> None:
    """A publisher that can never complete a round would hold the arm with nothing said."""
    with pytest.raises(ValueError, match="never complete a round"):
        AcceptedTargetPublisher(TargetMailbox(), ManualClock(), ())


def test_the_publish_order_is_the_frozen_arm_major_layout() -> None:
    """The side order the publisher assembles in is the order CTR-ACT froze.

    Index i of the bimanual vector names one physical joint
    (`contracts/action_observation.yaml` `joints`). Assembling it in the other arm order sends
    the left arm's angles to the right arm, and both arms move — to each other's targets.
    """
    document: dict[str, Any] = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert tuple(document["joints"]["arms"]) == SIDE_PREFIXES
