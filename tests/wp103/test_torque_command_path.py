"""FR-MOT-058 — the torque command path: `send_action` routes tau, and refuses out of band.

LeRobot's stock `send_action` builds `(kp, kd, position_degrees, 0.0, 0.0)`
(`openarm_follower.py:340`), so a feed-forward torque never left the follower even
though `_mit_control_batch` has taken one all along (`damiao.py:492-502`). Releasing
that hardcode is routing a torque into the same filtered decision the position takes.

Two properties this file exists to hold, because both are load-bearing before a
brakeless 40 Nm arm:

- A command carrying no torque behaves exactly as it did: the gateway sees `None`,
  not a vector of zeros, so no existing caller's decision changes shape.
- An out-of-band torque is refused, never clamped. The band is the URDF effort limit,
  which is tighter than Peak Torque on J5-J7 (7 vs 10 Nm), so the gateway's own peak
  clamp cannot silently rescue a value this path admits — and a clamp here would send
  a torque the caller never asked for instead of stopping them.

The gripper slot is refused on every build: this rig carries a fixed spatula and CAN
id 0x08 is not a motor, and even a fitted gripper takes a per-unit current limit rather
than newton-metres (`03` FR-MOT-047).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from backend.actuation import BusCanWriter, SafetyReason, positions_to_batch
from backend.actuation.config import MIT_HOLD_KD, MIT_HOLD_KP
from backend.calibration.schema import MOTOR_COUNT, MOTOR_ORDER
from backend.endeffector import EndEffectorError, default_profile, gripper_build
from backend.threshold.constants import JOINT_EFFORT_LIMITS_NM
from contracts.recorder.schema import TORQUE_SUFFIX
from contracts.units import Deg, deg_to_rad
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    FEEDFORWARD_TORQUE_LIMIT_NM,
    GRIPPER_MOTOR_NAME,
    NO_FEEDFORWARD_TORQUE_NM,
    PEAK_TORQUE_NM,
    SIDE_PREFIXES,
    BiOaOpenArmFollower,
    GainRefusedError,
    OaOpenArmFollower,
    TorqueRefusedError,
)

# A move small enough to clear every rate guard on the first command from rest: 1 deg in
# one 20 ms period is 0.87 rad/s against a 1.57 rad/s shoulder ceiling.
SMALL_MOVE_DEG = 1.0

# Joint indices used by the band cases. J1 is a DM8009 shoulder (40 Nm effort, equal to
# its peak); J5 is a DM4310 wrist, where the effort band (7) is strictly inside the peak
# (10) and so is the only place the two bounds can be told apart.
SHOULDER_INDEX = 0
WRIST_INDEX = 4
SHOULDER_MOTOR = MOTOR_ORDER[SHOULDER_INDEX]
WRIST_MOTOR = MOTOR_ORDER[WRIST_INDEX]
WRIST_EFFORT_NM = JOINT_EFFORT_LIMITS_NM[WRIST_INDEX]
SHOULDER_EFFORT_NM = JOINT_EFFORT_LIMITS_NM[SHOULDER_INDEX]

# How far past a bound a case goes. Large enough to survive float formatting, small
# enough that the value would still be inside the wrist's Peak Torque — which is the
# point: only the effort band refuses it.
BAND_OVERSHOOT_NM = 0.1

# An in-band torque for the routing case, comfortably inside both bounds.
ROUTED_SHOULDER_TORQUE_NM = 5.0
ROUTED_WRIST_TORQUE_NM = 6.5

# A shoulder torque above every wrist's band (7) and well inside the shoulder's own (40).
# The band is per-joint, so this value has to be admitted; one global ceiling would refuse it
# and leave the two 40 Nm joints commandable only up to a wrist's figure.
ABOVE_WRIST_BAND_SHOULDER_TORQUE_NM = 20.0

# A position far enough past the present pose to trip a rate guard on the first command:
# 30 deg in one 20 ms period is 26 rad/s against the 1.57 rad/s shoulder ceiling.
RATE_GUARD_TRIPPING_MOVE_DEG = 30.0

# A per-joint damping of zero — admissible to the encoder, refused under a driving stiffness
# (`03` FR-MOT-021).
ZERO_KD = 0.0

# A per-joint stiffness of zero: the pure feed-forward frame `04` §2.8 admits, and the only
# state in which zero damping is legal. It is what makes a dropped `custom_kp` visible — the
# same command with the hold stiffness instead is the refused pair.
ZERO_KP = 0.0

# A motor name outside the frozen eight-slot layout.
UNKNOWN_MOTOR = "joint_9"


class RecordingMitBus:
    """A fake MIT bus that keeps the last batched command dict it was handed."""

    def __init__(self) -> None:
        """Start with nothing sent."""
        self.sent: dict[str, tuple[float, float, float, float, float]] | None = None

    def _mit_control_batch(
        self, commands: dict[str, tuple[float, float, float, float, float]]
    ) -> None:
        """Record one batch; no CAN, no motor."""
        self.sent = commands


def small_move() -> dict[str, float]:
    """A position action that clears every rate guard on the first command from rest.

    The gripper slot is left out so it holds at present: this arm has no gripper motor,
    and the left arm's gripper limit would clamp any positive angle anyway.
    """
    return {f"{motor}.pos": SMALL_MOVE_DEG for motor in MOTOR_ORDER[:-1]}


def send_to_bus(follower: OaOpenArmFollower) -> RecordingMitBus:
    """Carry the follower's accepted command onto the writer the single writer uses.

    The follower holds no CAN handle, so the last hop is done here: the accepted degrees
    and the accepted feed-forward torque become one `ExecutedMitCommand` per motor and go
    through `BusCanWriter`, which is what turns them into the `_mit_control_batch` 5-tuple.
    The batch is built over the motors the fitted tool actually puts on the bus — seven on
    this rig — because addressing the absent 0x08 walks the controller to ERROR-PASSIVE.

    Args:
        follower: A follower whose last `send_action` was accepted.

    Returns:
        (RecordingMitBus) The fake bus holding the batch that would have been sent.
    """
    result = follower.last_gate_result
    assert result is not None
    fitted = default_profile().motor_count
    batch = positions_to_batch(
        tuple(deg_to_rad(angle) for angle in result.accepted[:fitted]),
        result.feedforward_torque_nm[:fitted],
    )
    bus = RecordingMitBus()
    BusCanWriter(bus, MOTOR_ORDER[:fitted]).mit_control_batch(batch)
    return bus


def test_no_torque_argument_hands_the_gateway_none_not_zeros(
    make_follower: Callable[..., OaOpenArmFollower],
) -> None:
    """Omitting the torque leaves the gateway call byte-identical to before this path."""
    follower = make_follower()
    seen: list[object] = []
    submit = follower.gateway.submit

    def spy(*args: object, **kwargs: object) -> object:
        seen.append(kwargs.get("feedforward_torque_nm", "absent"))
        return submit(*args, **kwargs)

    follower.gateway.submit = spy  # type: ignore[method-assign]

    follower.send_action(small_move())

    # None, not an all-zero vector: the two are distinct inputs to the filter, and the
    # pre-existing behaviour is the None one.
    assert seen == [None]


def test_no_torque_argument_returns_the_position_only_action(
    make_follower: Callable[..., OaOpenArmFollower],
) -> None:
    """The returned action is the same position-only key set it always was."""
    follower = make_follower()

    applied = follower.send_action(small_move())

    assert set(applied) == {f"{motor}.pos" for motor in MOTOR_ORDER}
    # Uncalibrated, the gateway holds at present — unchanged by this path existing.
    assert all(value == 0.0 for value in applied.values())
    assert follower.last_gate_result is not None
    assert follower.last_gate_result.reason is SafetyReason.ZERO_UNCALIBRATED


def test_the_returned_action_never_carries_a_torque_dimension(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Torque rides beside the action, never inside it — a torque in `action` is FAIL_BLOCKING.

    CTR-REC@v1 records the returned action as the training target, so a `.torque` key here
    would train a policy on a channel that is not a position command (`07` §2.3.3).
    """
    follower = make_follower()

    applied = follower.send_action(
        small_move(),
        feedforward_torque_nm={SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM},
    )

    assert not [key for key in applied if key.endswith(TORQUE_SUFFIX)]


def test_a_position_only_command_still_carries_zero_accepted_torque(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """With no torque asked for, every joint's accepted feed-forward torque is zero."""
    follower = make_follower()

    follower.send_action(small_move())

    result = follower.last_gate_result
    assert result is not None
    assert all(torque.value == NO_FEEDFORWARD_TORQUE_NM for torque in result.feedforward_torque_nm)


def test_in_band_torque_reaches_the_bus_tuple(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The commanded tau lands in the fifth `_mit_control_batch` element, not a zero."""
    follower = make_follower()

    follower.send_action(
        small_move(),
        feedforward_torque_nm={
            SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM,
            WRIST_MOTOR: ROUTED_WRIST_TORQUE_NM,
        },
    )

    sent = send_to_bus(follower).sent
    assert sent is not None
    assert sent[SHOULDER_MOTOR][4] == ROUTED_SHOULDER_TORQUE_NM
    assert sent[WRIST_MOTOR][4] == ROUTED_WRIST_TORQUE_NM
    # The joints nobody commanded a torque on stay at zero rather than inheriting one.
    assert sent[MOTOR_ORDER[1]][4] == NO_FEEDFORWARD_TORQUE_NM
    # The position slot still carries the filtered position, so the torque rode along
    # with the command rather than replacing it.
    assert sent[SHOULDER_MOTOR][2] == pytest.approx(SMALL_MOVE_DEG)


def test_the_batch_addresses_only_the_motors_the_fitted_tool_puts_on_the_bus(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Seven motors, not eight: 0x08 is not on this bus and an unanswered frame degrades it."""
    follower = make_follower()

    follower.send_action(
        small_move(), feedforward_torque_nm={SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM}
    )

    sent = send_to_bus(follower).sent
    assert sent is not None
    assert GRIPPER_MOTOR_NAME not in sent
    assert len(sent) == default_profile().motor_count


def test_an_in_band_torque_is_not_clamped_on_the_way_through(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """A torque exactly at the effort limit comes out unchanged — admitted means unaltered.

    The wrist is the joint that can tell the two bounds apart: its effort limit is 7 Nm and
    its Peak Torque 10 Nm, so a value the effort band admits is never touched by the peak
    clamp behind it.
    """
    follower = make_follower()

    follower.send_action(small_move(), feedforward_torque_nm={WRIST_MOTOR: WRIST_EFFORT_NM})

    result = follower.last_gate_result
    assert result is not None
    assert result.feedforward_torque_nm[WRIST_INDEX].value == WRIST_EFFORT_NM


def test_the_negative_wrist_effort_limit_is_admitted_unaltered(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The band is two-sided: −7 Nm on a wrist is as admissible as +7, and as unaltered.

    A joint pulls as well as pushes, so a band tested only on its positive half leaves the
    negative half to whatever the peak clamp happens to allow — 10 Nm here, not 7.
    """
    follower = make_follower()

    follower.send_action(small_move(), feedforward_torque_nm={WRIST_MOTOR: -WRIST_EFFORT_NM})

    result = follower.last_gate_result
    assert result is not None
    assert result.feedforward_torque_nm[WRIST_INDEX].value == -WRIST_EFFORT_NM


def test_a_shoulder_torque_above_the_wrist_band_is_admitted_unaltered(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """20 Nm on a 40 Nm shoulder passes: the band is per-joint, not one number for the arm.

    Without this, a band collapsed to the smallest joint's figure would still refuse every
    over-command the other cases try, and nothing would notice the arm had lost two thirds
    of its shoulder authority.
    """
    follower = make_follower()

    follower.send_action(
        small_move(),
        feedforward_torque_nm={SHOULDER_MOTOR: ABOVE_WRIST_BAND_SHOULDER_TORQUE_NM},
    )

    result = follower.last_gate_result
    assert result is not None
    assert ABOVE_WRIST_BAND_SHOULDER_TORQUE_NM > WRIST_EFFORT_NM
    assert result.feedforward_torque_nm[SHOULDER_INDEX].value == (
        ABOVE_WRIST_BAND_SHOULDER_TORQUE_NM
    )


def test_the_refusal_band_is_contained_in_peak_torque() -> None:
    """Every effort bound is inside its joint's Peak Torque, so FR-MOT-037 holds by containment.

    Widening a joint's effort figure past its peak would make this path admit a torque the
    hardware bound forbids, and no other check would catch it.
    """
    assert len(FEEDFORWARD_TORQUE_LIMIT_NM) == MOTOR_COUNT
    for index, ceiling in enumerate(FEEDFORWARD_TORQUE_LIMIT_NM):
        if ceiling is not None:
            assert ceiling <= PEAK_TORQUE_NM[index]


def test_a_torque_above_the_effort_limit_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Past the wrist's 7 Nm effort limit the command stops, though 10 Nm Peak would allow it."""
    follower = make_follower()

    with pytest.raises(TorqueRefusedError):
        follower.send_action(
            small_move(),
            feedforward_torque_nm={WRIST_MOTOR: WRIST_EFFORT_NM + BAND_OVERSHOOT_NM},
        )


def test_a_torque_below_the_negative_effort_limit_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The band is symmetric: a large negative torque is as refused as a large positive one."""
    follower = make_follower()

    with pytest.raises(TorqueRefusedError):
        follower.send_action(
            small_move(),
            feedforward_torque_nm={SHOULDER_MOTOR: -(SHOULDER_EFFORT_NM + BAND_OVERSHOOT_NM)},
        )


def test_a_torque_below_the_negative_wrist_limit_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """−7.1 Nm on a wrist is refused by the band, though −10 Nm Peak Torque would allow it.

    This is the case the positive half cannot stand in for: the wrist is the only joint whose
    effort figure is strictly inside its peak, so a lower bound that fell back to the peak
    would pass every other case in this file and admit 10 Nm of pull on a 7 Nm joint.
    """
    follower = make_follower()

    with pytest.raises(TorqueRefusedError):
        follower.send_action(
            small_move(),
            feedforward_torque_nm={WRIST_MOTOR: -(WRIST_EFFORT_NM + BAND_OVERSHOOT_NM)},
        )


def test_the_refusal_names_the_joint_and_the_limit(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The message identifies the offending joint, its bound, and that nothing was clamped."""
    follower = make_follower()

    with pytest.raises(TorqueRefusedError) as refusal:
        follower.send_action(
            small_move(),
            feedforward_torque_nm={WRIST_MOTOR: WRIST_EFFORT_NM + BAND_OVERSHOOT_NM},
        )

    message = str(refusal.value)
    assert WRIST_MOTOR in message
    assert f"{WRIST_EFFORT_NM:.4g}" in message
    assert "refused, not clamped" in message


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_non_finite_torque_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
    value: float,
) -> None:
    """NaN and the infinities are outside every band; a comparison that passes them is broken."""
    follower = make_follower()

    with pytest.raises(TorqueRefusedError):
        follower.send_action(small_move(), feedforward_torque_nm={SHOULDER_MOTOR: value})


def test_an_unknown_motor_name_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """A key outside the frozen layout stops the command instead of quietly commanding zero."""
    follower = make_follower()

    with pytest.raises(TorqueRefusedError) as refusal:
        follower.send_action(
            small_move(), feedforward_torque_nm={UNKNOWN_MOTOR: ROUTED_SHOULDER_TORQUE_NM}
        )

    assert UNKNOWN_MOTOR in str(refusal.value)


def test_a_refused_torque_never_reaches_the_gateway(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Refusal happens before the gateway, so a refused command leaves no decision behind."""
    follower = make_follower()

    with pytest.raises(TorqueRefusedError):
        follower.send_action(
            small_move(),
            feedforward_torque_nm={WRIST_MOTOR: WRIST_EFFORT_NM + BAND_OVERSHOOT_NM},
        )

    assert follower.gateway.frames == ()
    assert follower.last_gate_result is None


def test_a_nonzero_gripper_torque_is_refused_by_the_end_effector(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """On the fitted spatula there is no motor 0x08, and the refusal comes from the tool."""
    follower = make_follower()

    with pytest.raises(EndEffectorError) as refusal:
        follower.send_action(
            small_move(),
            feedforward_torque_nm={GRIPPER_MOTOR_NAME: ROUTED_SHOULDER_TORQUE_NM},
        )

    message = str(refusal.value)
    assert "0x08" in message
    assert "Refused rather than dropped" in message


def test_a_zero_gripper_torque_is_admitted(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """Filling the frozen slot with zero states "no gripper action", so it is not a request."""
    follower = make_follower()

    follower.send_action(
        small_move(),
        feedforward_torque_nm={GRIPPER_MOTOR_NAME: NO_FEEDFORWARD_TORQUE_NM},
    )

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected


def test_a_gripper_torque_is_refused_even_on_an_arm_that_has_one(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """A fitted gripper takes a per-unit current limit, never newton-metres (FR-MOT-047)."""
    follower = make_follower(end_effector=gripper_build())

    with pytest.raises(TorqueRefusedError) as refusal:
        follower.send_action(
            small_move(),
            feedforward_torque_nm={GRIPPER_MOTOR_NAME: ROUTED_SHOULDER_TORQUE_NM},
        )

    assert GRIPPER_MOTOR_NAME in str(refusal.value)


def test_a_filter_rejection_strips_the_torque(
    make_follower: Callable[..., OaOpenArmFollower],
) -> None:
    """A command the filter stops carries no torque out — a held arm is not a pushed one."""
    follower = make_follower()

    follower.send_action(
        small_move(),
        feedforward_torque_nm={SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM},
    )

    result = follower.last_gate_result
    assert result is not None
    # Uncalibrated: the ZERO stage stops it.
    assert result.rejected
    assert all(torque.value == NO_FEEDFORWARD_TORQUE_NM for torque in result.feedforward_torque_nm)


def test_the_torque_still_passes_through_the_ordered_filter(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """A torque does not buy a position past the rate guards — the filter runs unchanged."""
    follower = make_follower()
    far = {f"{motor}.pos": RATE_GUARD_TRIPPING_MOVE_DEG for motor in MOTOR_ORDER[:-1]}

    applied = follower.send_action(
        far, feedforward_torque_nm={SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM}
    )

    result = follower.last_gate_result
    assert result is not None
    assert result.rejected
    assert applied[f"{SHOULDER_MOTOR}.pos"] == Deg(0.0).value


def test_commanding_a_torque_enables_no_torque(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """This is the command path; engaging torque is WP-1-05's, after PG-SAFE-001."""
    follower = make_follower()

    follower.send_action(
        small_move(),
        feedforward_torque_nm={SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM},
    )

    assert follower.is_torque_enabled is False


def test_zero_damping_with_a_live_torque_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The pair that made a probe send 20 Nm at kd=0 now holds instead (`03` FR-MOT-021).

    The command names no stiffness, so every joint carries the hold stiffness, which drives a
    position; Damiao's own documentation says a position command at kd=0 vibrates or runs away,
    and this one would carry half a shoulder's rated torque while doing it.
    """
    follower = make_follower()

    follower.send_action(
        small_move(),
        custom_kd=dict.fromkeys(MOTOR_ORDER, ZERO_KD),
        feedforward_torque_nm={SHOULDER_MOTOR: ABOVE_WRIST_BAND_SHOULDER_TORQUE_NM},
    )

    result = follower.last_gate_result
    assert result is not None
    assert result.rejected
    assert result.reason is SafetyReason.KD_ZERO_POSITION_CONTROL
    assert all(torque.value == NO_FEEDFORWARD_TORQUE_NM for torque in result.feedforward_torque_nm)


def test_zero_damping_on_one_joint_is_refused_when_another_joint_names_a_gain(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """kp and kd are judged per joint, so naming them on different joints cannot dodge the rule.

    A gain vector compacted to whatever the caller happened to name pairs the first stiffness
    with the first damping — here joint_1's kp=0 with joint_5's kd=0 — and concludes there is
    no position control anywhere. joint_5 is in fact on the hold stiffness and would be sent
    the forbidden pair.
    """
    follower = make_follower()

    follower.send_action(
        small_move(),
        custom_kp={SHOULDER_MOTOR: 0.0},
        custom_kd={WRIST_MOTOR: ZERO_KD},
    )

    result = follower.last_gate_result
    assert result is not None
    assert result.rejected
    assert result.reason is SafetyReason.KD_ZERO_POSITION_CONTROL


def test_the_hold_damping_still_reaches_the_gateway(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """The hold gains must stay admissible, or the arm loses its way to hold position."""
    follower = make_follower()

    follower.send_action(small_move(), custom_kd=dict.fromkeys(MOTOR_ORDER, MIT_HOLD_KD))

    result = follower.last_gate_result
    assert result is not None
    assert not result.rejected


def test_a_gain_naming_an_unknown_motor_is_refused(
    make_follower: Callable[..., OaOpenArmFollower],
    calibrated: None,
) -> None:
    """A mistyped gain key stops the command instead of leaving that joint on the hold gains."""
    follower = make_follower()

    with pytest.raises(GainRefusedError) as refusal:
        follower.send_action(small_move(), custom_kp={UNKNOWN_MOTOR: MIT_HOLD_KP})

    assert UNKNOWN_MOTOR in str(refusal.value)


def bimanual_move() -> dict[str, float]:
    """The small move, addressed to both arms under their channel prefixes."""
    return {
        f"{side}_{motor}.pos": SMALL_MOVE_DEG
        for side in SIDE_PREFIXES
        for motor in MOTOR_ORDER[:-1]
    }


def test_the_bimanual_routes_a_torque_to_the_arm_that_was_named(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """`bi_oa_openarm_follower` is the registered type this rig runs, so tau must arrive here.

    Reaching into `.left_arm` to command a torque is not the same thing: it leaves the other
    arm commanded by whoever held it last, which is the state the single enforcement point
    exists to make impossible.
    """
    pair = make_bimanual()

    pair.send_action(
        bimanual_move(),
        feedforward_torque_nm={f"left_{SHOULDER_MOTOR}": ROUTED_SHOULDER_TORQUE_NM},
    )

    left = pair.left_arm.last_gate_result
    right = pair.right_arm.last_gate_result
    assert left is not None
    assert right is not None
    assert left.feedforward_torque_nm[SHOULDER_INDEX].value == ROUTED_SHOULDER_TORQUE_NM
    assert all(torque.value == NO_FEEDFORWARD_TORQUE_NM for torque in right.feedforward_torque_nm)


def test_the_bimanual_refuses_an_out_of_band_torque(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """The per-arm band is what the pair enforces; it does not widen by being reached through."""
    pair = make_bimanual()

    with pytest.raises(TorqueRefusedError):
        pair.send_action(
            bimanual_move(),
            feedforward_torque_nm={f"right_{WRIST_MOTOR}": WRIST_EFFORT_NM + BAND_OVERSHOOT_NM},
        )


def test_the_bimanual_refuses_a_torque_key_that_names_no_arm(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """An unsided key reaches neither arm, so the joint the caller meant would get zero."""
    pair = make_bimanual()

    with pytest.raises(TorqueRefusedError) as refusal:
        pair.send_action(
            bimanual_move(),
            feedforward_torque_nm={SHOULDER_MOTOR: ROUTED_SHOULDER_TORQUE_NM},
        )

    assert SHOULDER_MOTOR in str(refusal.value)


def test_the_bimanual_routes_gains_and_the_kd_rule_holds_per_arm(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """Zero damping on the left is refused for the left, and the right is judged on its own."""
    pair = make_bimanual()

    pair.send_action(
        bimanual_move(),
        custom_kd={f"left_{motor}": ZERO_KD for motor in MOTOR_ORDER},
    )

    left = pair.left_arm.last_gate_result
    right = pair.right_arm.last_gate_result
    assert left is not None
    assert right is not None
    assert left.reason is SafetyReason.KD_ZERO_POSITION_CONTROL
    assert not right.rejected


def test_the_bimanual_refuses_a_gain_key_that_names_no_arm(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """An unsided gain key would leave the joint on the hold stiffness without saying so."""
    pair = make_bimanual()

    with pytest.raises(GainRefusedError):
        pair.send_action(bimanual_move(), custom_kp={SHOULDER_MOTOR: ZERO_KP})


def test_the_bimanual_refuses_a_position_key_that_names_no_arm(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """An unsided position key filters to nothing on both arms and the move vanishes silently.

    The gains and the torque are already refused for this; the position keys are the channel a
    caller actually types most often, and a dropped one leaves that joint holding at present
    while every other joint moves — which reads as an arm that partly obeyed.
    """
    pair = make_bimanual()
    unsided = f"{SHOULDER_MOTOR}.pos"

    with pytest.raises(ValueError) as refusal:
        pair.send_action({**bimanual_move(), unsided: SMALL_MOVE_DEG})

    assert unsided in str(refusal.value)


def test_a_refused_torque_leaves_neither_arm_commanded(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """The pair is judged whole: a refusal on the second arm must not land the first one's frame.

    Refusing inside the split is refusing halfway through it. The caller gets an exception and no
    way to learn that one arm is already holding a new commanded pose while the other is still on
    whatever it had — the exact one-arm-commanded state this class exists to make impossible.
    """
    pair = make_bimanual()

    with pytest.raises(TorqueRefusedError):
        pair.send_action(
            bimanual_move(),
            feedforward_torque_nm={f"right_{WRIST_MOTOR}": WRIST_EFFORT_NM + BAND_OVERSHOOT_NM},
        )

    assert pair.left_arm.gateway.frames == ()
    assert pair.right_arm.gateway.frames == ()
    assert pair.left_arm.last_gate_result is None
    assert pair.right_arm.last_gate_result is None


def test_a_refused_gain_leaves_neither_arm_commanded(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """The same wholeness for gains: a mistyped motor on the right does not command the left."""
    pair = make_bimanual()

    with pytest.raises(GainRefusedError):
        pair.send_action(bimanual_move(), custom_kp={f"right_{UNKNOWN_MOTOR}": MIT_HOLD_KP})

    assert pair.left_arm.gateway.frames == ()
    assert pair.right_arm.gateway.frames == ()


def test_the_arm_the_caller_never_named_is_handed_nothing(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """Naming one arm says nothing about the other, so the other is handed None on every channel.

    An empty narrowing is not the same as no argument: it resolves to an eight-slot all-zero Nm
    vector, a commanded zero torque on every joint, where None is the position-only case the
    gateway takes. Commanding an arm the caller never mentioned is what the split must not do.
    """
    pair = make_bimanual()
    seen: list[tuple[object, object, object]] = []
    submit = pair.right_arm.gateway.submit

    def spy(*args: object, **kwargs: object) -> object:
        seen.append((kwargs.get("feedforward_torque_nm"), kwargs.get("kp"), kwargs.get("kd")))
        return submit(*args, **kwargs)

    pair.right_arm.gateway.submit = spy  # type: ignore[method-assign]

    pair.send_action(
        bimanual_move(),
        custom_kp={f"left_{SHOULDER_MOTOR}": MIT_HOLD_KP},
        custom_kd={f"left_{SHOULDER_MOTOR}": MIT_HOLD_KD},
        feedforward_torque_nm={f"left_{SHOULDER_MOTOR}": ROUTED_SHOULDER_TORQUE_NM},
    )

    assert seen == [(None, None, None)]


def test_the_bimanual_forwards_the_stiffness_that_makes_zero_damping_legal(
    make_bimanual: Callable[..., BiOaOpenArmFollower],
    calibrated: None,
) -> None:
    """kp=0 with kd=0 is the pure-torque frame, and it is only legal if the kp actually arrived.

    A stiffness dropped on the way to the arm leaves that joint on the hold stiffness, which
    drives a position, and the identical command becomes the refused (kp>0, kd=0) pair. So the
    arm's own verdict is what says whether the stiffness was forwarded — a gain the gateway never
    receives leaves no other trace, and the accepted action looks the same either way.
    """
    pair = make_bimanual()

    pair.send_action(
        bimanual_move(),
        custom_kp={f"left_{motor}": ZERO_KP for motor in MOTOR_ORDER},
        custom_kd={f"left_{motor}": ZERO_KD for motor in MOTOR_ORDER},
    )

    left = pair.left_arm.last_gate_result
    right = pair.right_arm.last_gate_result
    assert left is not None
    assert not left.rejected
    assert right is not None
    assert not right.rejected
