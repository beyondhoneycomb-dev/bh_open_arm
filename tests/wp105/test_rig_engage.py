"""The rig binding: what reaches the bus at torque-ON, and what refuses before it does.

The engage drives the real write path — `send_action` filters, the publisher fills the mailbox,
one scheduler tick writes — so these run the production spine over a fake CAN backend and a
manual clock. What is asserted is never "a call happened" but which motors it addressed, in what
order, and what angles the frame carried.

Both arms sit at different present angles throughout. With both halves at one angle a bimanual
frame assembled in the wrong arm order reads exactly like a correct one, and the whole point of
the arm-order refusals would be untestable.

The engage's command is the pose the arm reported, which makes it the one command whose two
possible verdicts produce the same frame: admitted it holds there, refused it holds at present,
and present is what it asked for. That is stated as its own case, because it is what lets the
engage route through a filter that is free to refuse it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from backend.actuation import (
    AcceptedTargetPublisher,
    Emission,
    EmissionLabel,
    FaultInjectionHarness,
    ReasonCode,
)
from backend.actuation.config import LEASE_DURATION_SEC
from backend.calibration.schema import MOTOR_ORDER
from backend.endeffector import GRIPPER_SEND_ID, SIDES, EndEffectorProfile, spatula_build
from backend.preflight import PreflightReport
from backend.torque_bringup import (
    SEND_ID_BY_MOTOR,
    AssembledRig,
    EngageBusUnassembledError,
    FittedMotorMismatchError,
    GuardedTorqueOn,
    SafeHoldViolationError,
    TorqueEngageSequenceError,
    TorqueOnManifest,
    assert_safe_hold,
    assert_targets_are_present_pose,
    build_engage_bus,
    build_present_pose_hold,
    fitted_motor_names,
)
from backend.torque_bringup.reverify import (
    assert_capture_addressed_fitted_motors,
    fixture_dir_from_env,
)
from contracts.action import ExecutedMitCommand
from contracts.plugin.config import Side
from contracts.units import Deg, Nm, Rad, RadPerSec, deg_to_rad
from packages.lerobot_robot_openarm.config_oa import (
    BiOaOpenArmFollowerConfig,
    OaOpenArmFollowerConfig,
)
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BiOaOpenArmFollower,
    OaOpenArmFollower,
)

# Present angles, per arm and per joint. Distinct across arms so a swapped half is visible in the
# emitted frame, and distinct across joints so a mis-slotted joint is too. Small enough to sit
# inside every URDF joint limit, so the LIMIT stage clamps nothing and the frame that leaves is
# the pose that was read.
LEFT_BASE_DEG = 1.0
RIGHT_BASE_DEG = 5.0
JOINT_STEP_DEG = 0.25

# What the bus reports for the gripper slot on a spatula build: nothing answers on 0x08, so the
# bus's own state cache is what a caller reading it back gets.
UNFITTED_SLOT_DEG = 0.0

# How far a drifted hold frame targets away from the pose that was read, degrees' worth in
# radians. Any non-zero value is refused; this one is unmistakable in the message.
DRIFT_RAD = 0.2

# A hold frame with no restoring stiffness — a drop wearing a hold's angles.
LIMP_KP = 0.0

# Maintenance ticks driven after an engage, and the drift the hold angles are allowed across
# them: none, because a maintained hold re-sends the same frame.
MAINTENANCE_TICKS = 5
NO_DRIFT_RAD = 0.0

# How far past the lease duration the clock is pushed to lapse the deadman before an engage. Two
# whole durations, so the lapse is unambiguous rather than sitting on the boundary.
LAPSED_LEASE_MULTIPLE = 2.0

# The capture block the deferred hardware hook reads. Named once so the synthetic captures and
# the real one cannot drift apart inside this file.
ENGAGE_BLOCK = "rig_engage"
SEND_IDS_KEY = "send_ids"
PRESENT_KEY = "present_pose_rad"
FRAME_KEY = "engaged_frame"

# Gains a captured engage frame carries. Read off the capture rather than recomputed, so a value
# here is only the input to the judgment and never the thing asserted.
CAPTURED_KP = 40.0
CAPTURED_KD = 1.0
CAPTURED_DQ_RAD_S = 0.0
CAPTURED_TAU_NM = 0.0

_REAL_FIXTURE = fixture_dir_from_env()
_SKIP_REASON = (
    "the frame the single writer put on can0/can1 for the guarded engage, and the fitted motors "
    "it held: requires the arm powered, a real CAN adapter and a PG-SAFE-001 PASS (12 FR-SAF-075, "
    "16 M-2); set OPENARM_TORQUE_BRINGUP_REAL_FIXTURE to a real capture directory to re-verify"
)


class RigEngageMissingError(AssertionError):
    """Raised when a capture carries no record of what the engage put on the bus.

    An `AssertionError` deliberately: a supplied capture that cannot answer the question is a
    failed acceptance, not a configuration problem to skip past.
    """


class RecordingArmBus:
    """One arm's bus double: answers reads and records which motors every call addressed.

    The recorded argument is the whole point. A bus call that names no motors walks every motor
    the bus was constructed with, which on a spatula build is the id nothing answers on, and the
    only way to tell the two apart from outside is to keep what was asked for.

    Attributes:
        log: Method names in call order, shared with the other arm and the spine so one sequence
            covers the whole engage.
        read_motors: The motor lists handed to each `sync_read_all_states`, in call order; None
            for a call that named none.
        enabled_motors: The motor lists handed to each `enable_torque`, in call order.
        dropped_motors: The motor lists handed to each `drop_torque`, in call order.
    """

    def __init__(
        self,
        side: str,
        base_deg: float,
        log: list[str],
        unanswered: tuple[str, ...] = (),
    ) -> None:
        """Build a bus reporting a distinct angle per joint.

        Args:
            side: Which arm this bus belongs to, for the call log.
            base_deg: The first joint's angle; each later joint steps up from it.
            log: The shared call log.
            unanswered: Fitted motors this bus answers no state for — a motor that was polled
                and said nothing.
        """
        self._side = side
        self._unanswered = unanswered
        self.motors = list(MOTOR_ORDER)
        self.log = log
        self.read_motors: list[list[str] | None] = []
        self.enabled_motors: list[list[str]] = []
        self.dropped_motors: list[list[str]] = []
        self._angles = {
            motor: base_deg + JOINT_STEP_DEG * index for index, motor in enumerate(MOTOR_ORDER[:-1])
        }
        # The gripper slot is in the frozen layout and its motor is not on this bus, so what a
        # read of it returns is the bus's own cache rather than an answer from a motor.
        self._angles[MOTOR_ORDER[-1]] = UNFITTED_SLOT_DEG

    def sync_read_all_states(self, motors: list[str] | None = None) -> dict[str, dict[str, float]]:
        """Return one state per named motor, or per registered motor when none are named."""
        self.log.append(f"{self._side}:read")
        self.read_motors.append(None if motors is None else list(motors))
        named = list(self.motors) if motors is None else motors
        return {
            motor: {"position": self._angles[motor], "velocity": 0.0, "torque": 0.0}
            for motor in named
            if motor not in self._unanswered
        }

    def enable_torque(self, motors: list[str]) -> None:
        """Record a 0xFC and the motors it addressed."""
        self.log.append(f"{self._side}:enable")
        self.enabled_motors.append(list(motors))

    def drop_torque(self, motors: list[str]) -> None:
        """Record a 0xFD and the motors it addressed."""
        self.log.append(f"{self._side}:drop")
        self.dropped_motors.append(list(motors))


class RecordingSpine:
    """The harness spine with its ticks written into the shared call log.

    What the engage promises is an order — the enable and the first frame after it are one call —
    and an order is only observable if the writes and the bus calls land in one sequence.
    """

    def __init__(self, inner: Any, log: list[str]) -> None:
        """Wrap a spine, logging every tick.

        Args:
            inner: The real `ActuationScheduler` this delegates to.
            log: The shared call log.
        """
        self._inner = inner
        self._log = log

    def renew_lease(self) -> None:
        """Renew the deadman on the wrapped spine."""
        self._inner.renew_lease()

    def tick(self) -> Emission:
        """Log the tick and run it."""
        self._log.append("tick")
        return self._inner.tick()


class _SpineThatHoldsAfterTheEnable:
    """A spine whose first tick carries the target and whose second emits a hold instead.

    The engage drives the write path twice: once with torque still off, to prove the path carries
    this session's pose, and once immediately after 0xFC. Only the second tick reaches an
    energized motor, and only a double that behaves differently across the two can tell whether
    the check on that second frame fires at all.

    The failure it injects is the one the check names: a lease that lapsed, a mailbox overwritten,
    a round that never completed. Any of them makes the tick emit the spine's cached frame, which
    is a pose from before this engage — on a brakeless arm, a pose to snap to.
    """

    def __init__(self, inner: Any, log: list[str]) -> None:
        """Wrap a spine, holding on every tick after the first.

        Args:
            inner: The real spine this delegates to.
            log: The shared call log.
        """
        self._inner = inner
        self._log = log
        self._ticks = 0

    def renew_lease(self) -> None:
        """Renew the deadman on the wrapped spine."""
        self._inner.renew_lease()

    def tick(self) -> Emission:
        """Carry the target once, then hold."""
        self._log.append("tick")
        self._ticks += 1
        emission = self._inner.tick()
        if self._ticks == 1:
            return emission
        return Emission(
            label=EmissionLabel.STALE_SOURCE_HOLD,
            reason=ReasonCode.MAILBOX_STALE,
            batch=emission.batch,
        )


class _Rig:
    """One assembled bench rig: the pair, the spine, the two bus doubles, and the call log."""

    def __init__(
        self,
        tmp_path: Path,
        publisher_wired: bool = True,
        unanswered: tuple[str, ...] = (),
        swap_arms: bool = False,
        publisher_sides: tuple[str, ...] = SIDES,
        joint_limits: tuple[tuple[Deg, Deg] | None, ...] | None = None,
    ) -> None:
        """Stand up the whole write path over a fake CAN backend and a manual clock.

        Args:
            tmp_path: Calibration directory for the two arms.
            publisher_wired: Whether the arms hold the publisher that fills this spine's mailbox.
            unanswered: Fitted motors the left bus answers no state for.
            swap_arms: Whether to put the right-side arm in the left slot, the wiring fault the
                arm-order refusal exists for.
            publisher_sides: The order the publisher assembles the two halves in.
            joint_limits: Per-joint clamp bounds the spine applies to a published target.
        """
        self.log: list[str] = []
        self.harness = FaultInjectionHarness(joint_limits=joint_limits)
        publisher = (
            AcceptedTargetPublisher(self.harness.mailbox, self.harness.clock, publisher_sides)
            if publisher_wired
            else None
        )
        self.buses = {
            SIDES[0]: RecordingArmBus(SIDES[0], LEFT_BASE_DEG, self.log, unanswered),
            SIDES[1]: RecordingArmBus(SIDES[1], RIGHT_BASE_DEG, self.log),
        }
        left_side = Side.RIGHT if swap_arms else Side.LEFT

        def arm(side: Side, robot_id: str) -> OaOpenArmFollower:
            return OaOpenArmFollower(
                OaOpenArmFollowerConfig(side=side, id=robot_id, calibration_dir=tmp_path),
                bus=self.buses[side.value],
                end_effector=spatula_build(),
                clock=self.harness.clock,
                publisher=publisher,
            )

        self.pair = BiOaOpenArmFollower(
            BiOaOpenArmFollowerConfig(id="wp105_rig"),
            left=arm(left_side, "wp105_rig_left"),
            right=arm(Side.RIGHT, "wp105_rig_right"),
        )
        self.spine = RecordingSpine(self.harness.scheduler, self.log)

    def build(self) -> AssembledRig:
        """Wire the rig binding over this bench."""
        return build_engage_bus(
            spine=self.spine,
            pair=self.pair,
            buses=self.buses,
            end_effectors=_spatula_rig(),
        )


def _spatula_rig() -> Any:
    """The end-effector record for this bench: a fixed spatula on both arms."""
    from backend.endeffector import RigEndEffectors

    return RigEndEffectors(left=spatula_build(), right=spatula_build())


def _left_bus(rig: _Rig) -> RecordingArmBus:
    """The left arm's bus double."""
    return rig.buses[SIDES[0]]


def _present_deg(base_deg: float) -> tuple[Deg, ...]:
    """The fitted joints' present angles for an arm whose first joint sits at `base_deg`."""
    return tuple(
        Deg(base_deg + JOINT_STEP_DEG * index)
        for index in range(len(fitted_motor_names(spatula_build())))
    )


def _bimanual_hold_rad() -> tuple[Rad, ...]:
    """The sixteen angles a correct engage frame carries: each arm's present pose, arm-major."""
    unfitted = (Deg(UNFITTED_SLOT_DEG),)
    return tuple(
        deg_to_rad(angle)
        for angle in (
            *_present_deg(LEFT_BASE_DEG),
            *unfitted,
            *_present_deg(RIGHT_BASE_DEG),
            *unfitted,
        )
    )


def _emitted_angles(rig: _Rig) -> tuple[Rad, ...]:
    """The angles of the last frame the single writer sent."""
    batch = rig.harness.can_writer.last_batch
    assert batch is not None
    return tuple(command.q for command in batch)


def _engage(
    rig: AssembledRig,
    side: str,
    preflight: PreflightReport,
    manifest: TorqueOnManifest,
    profile: EndEffectorProfile | None = None,
) -> Any:
    """Run one guarded torque-ON over one arm of an assembled rig."""
    fitted = profile if profile is not None else spatula_build()
    return GuardedTorqueOn(rig.for_side(side), fitted, preflight, manifest).engage()


@pytest.fixture
def calibrated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report both arms as zeroed, so the filter admits the engage instead of refusing at ZERO."""
    monkeypatch.setattr(OaOpenArmFollower, "is_calibrated", property(lambda _self: True))


# --- The positive path: what actually reaches the bus ---


def test_the_engage_frame_the_single_writer_sends_is_the_pose_the_arm_reported(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    bench = _Rig(tmp_path)
    result = _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert result.send_ids == spatula_build().motor_send_ids
    assert set(result.commanded_displacement_rad()) == {0.0}
    # The frame on the bus is both arms' present pose, arm-major, and nothing else.
    assert _emitted_angles(bench) == _bimanual_hold_rad()
    assert_safe_hold(bench.harness.can_writer.last_batch)


def test_the_engage_reads_and_enables_only_the_fitted_motors(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # Motor 0x08 answered 0 of 20 polls on this bench. Every call the rig makes names its motors,
    # so no frame is addressed to it — the read included, which is the call a bare default would
    # have widened to all eight.
    bench = _Rig(tmp_path)
    fitted = fitted_motor_names(spatula_build())
    _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    bus = _left_bus(bench)
    assert bus.enabled_motors == [list(fitted)]
    assert [motors for motors in bus.read_motors if motors == list(fitted)]
    for motors in bus.read_motors:
        if motors is None:
            continue
        assert MOTOR_ORDER[-1] not in motors


def test_the_first_frame_after_the_enable_goes_out_inside_the_same_call(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """Between 0xFC and the first MIT frame a motor holds nothing, and this arm has no brake.

    The order also shows the proving tick: the write path carries this pose once while torque is
    still off, so a path that cannot carry it is found with nothing energized.
    """
    bench = _Rig(tmp_path)
    _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    enable_at = bench.log.index(f"{SIDES[0]}:enable")
    ticks = [index for index, entry in enumerate(bench.log) if entry == "tick"]
    assert [index for index in ticks if index < enable_at], "no frame proved the path before 0xFC"
    assert [index for index in ticks if index > enable_at], "0xFC left with no frame behind it"
    # And the enable is bracketed by the read that produced the pose it holds.
    assert bench.log.index(f"{SIDES[0]}:read") < enable_at


def test_both_arms_reach_the_writer_in_the_declared_order(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # The frame is one bimanual target: engaging the left arm carries the right arm's own
    # present-pose hold with it, in the right arm's slots.
    bench = _Rig(tmp_path)
    _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    emitted = _emitted_angles(bench)
    half = len(MOTOR_ORDER)
    assert emitted[0] == deg_to_rad(Deg(LEFT_BASE_DEG))
    assert emitted[half] == deg_to_rad(Deg(RIGHT_BASE_DEG))
    assert emitted[0] != emitted[half]


def test_the_engage_frame_is_the_same_whether_the_filter_admits_it_or_refuses_it(
    tmp_path: Path,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engage asks for the pose the arm is in, so both verdicts produce one frame.

    Without this the design claim is unchecked, and a filter refusal during an engage would look
    like a reason to route around the filter.
    """
    refused_bench = _Rig(tmp_path / "refused")
    _engage(refused_bench.build(), SIDES[0], passing_preflight, passing_manifest)
    refused = refused_bench.pair.left_arm.last_gate_result
    assert refused is not None
    assert refused.rejected

    monkeypatch.setattr(OaOpenArmFollower, "is_calibrated", property(lambda _self: True))
    admitted_bench = _Rig(tmp_path / "admitted")
    _engage(admitted_bench.build(), SIDES[0], passing_preflight, passing_manifest)
    admitted = admitted_bench.pair.left_arm.last_gate_result
    assert admitted is not None
    assert not admitted.rejected

    assert _emitted_angles(refused_bench) == _emitted_angles(admitted_bench)


def test_a_maintained_hold_keeps_sending_the_same_frame(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # An engage puts one frame out; the arm stays up because the frame keeps being sent. The
    # angles must not move while it is re-sent, and every tick must still be exactly one write.
    bench = _Rig(tmp_path)
    rig = bench.build()
    _engage(rig, SIDES[0], passing_preflight, passing_manifest)
    engaged = _emitted_angles(bench)
    writes = bench.harness.can_writer.write_count

    for _ in range(MAINTENANCE_TICKS):
        emission = rig.maintain_hold()
        assert_safe_hold(emission.batch)
        drift = max(
            abs(command.q.value - angle.value)
            for command, angle in zip(emission.batch, engaged, strict=True)
        )
        assert drift == NO_DRIFT_RAD

    assert bench.harness.can_writer.write_count == writes + MAINTENANCE_TICKS


# --- Refusals before 0xFC: nothing energized when the write path cannot carry the frame ---


def test_torque_stays_off_when_the_pair_publishes_into_no_mailbox(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """An arm built outside a torque-ON session filters, answers, and commands nothing.

    Enabling torque on it would leave a brakeless arm energized with no frame behind it, which is
    a sag rather than a hold. The proving tick is what turns that into a refusal.
    """
    bench = _Rig(tmp_path, publisher_wired=False)

    with pytest.raises(TorqueEngageSequenceError, match="mailbox_empty"):
        _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert _left_bus(bench).enabled_motors == []


def test_torque_stays_off_when_the_spine_is_latched(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # A latched spine emits its own hold on a cached frame rather than the published target. On a
    # brakeless arm that frame is a pose from before this engage, so 0xFC against it is a jump.
    bench = _Rig(tmp_path)
    bench.harness.latch()

    with pytest.raises(TorqueEngageSequenceError, match="SAFETY_LATCH_HOLD"):
        _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert _left_bus(bench).enabled_motors == []


def test_torque_stays_off_when_the_halves_are_assembled_in_the_other_arm_order(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """Index i of the frame names one physical joint, and can0 is the left arm by measurement.

    A publisher assembling the halves the other way round sends each arm the other one's angles,
    and both arms move. The emitted frame is a perfectly valid one — only the comparison against
    what the enforcement point decided per arm can see it.
    """
    bench = _Rig(tmp_path, publisher_sides=tuple(reversed(SIDES)))

    with pytest.raises(TorqueEngageSequenceError, match="not the one the eight-check filter"):
        _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert _left_bus(bench).enabled_motors == []


def test_torque_stays_off_when_the_spine_clamps_the_decided_frame(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # A bound applied after the filter has decided moves the target the filter admitted, so the
    # arm is commanded somewhere no decision authorized — here, away from where it is.
    pinned = tuple((Deg(0.0), Deg(0.0)) for _ in range(len(MOTOR_ORDER) * len(SIDES)))
    bench = _Rig(tmp_path, joint_limits=pinned)

    with pytest.raises(TorqueEngageSequenceError, match="not the one the eight-check filter"):
        _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert _left_bus(bench).enabled_motors == []


def test_an_engage_after_the_deadman_lapsed_still_carries_its_own_frame(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """A lease nobody renewed makes the tick emit the spine's cached frame instead of this pose.

    The cached frame is from before the engage — on a brakeless arm, a pose to snap to. So the
    engage renews the deadman on the tick that carries it, and the operator holding the arm is
    what the lease is standing in for at that instant.
    """
    bench = _Rig(tmp_path)
    bench.harness.clock.advance(LEASE_DURATION_SEC * LAPSED_LEASE_MULTIPLE)

    _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert _emitted_angles(bench) == _bimanual_hold_rad()
    assert _left_bus(bench).enabled_motors == [list(fitted_motor_names(spatula_build()))]


def test_the_first_frame_after_the_enable_is_checked_too(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    """The frame that reaches an energized motor is judged, not only the one that proved the path.

    The engage ticks twice, and the two ticks are not equivalent: the first runs with torque off,
    where a wrong frame moves nothing, and the second runs after 0xFC, where it is what the arm
    holds. Checking only the first would leave the one frame that reaches a live brakeless arm
    unjudged, and a cached hold there is a pose from before this engage to snap to.
    """
    bench = _Rig(tmp_path)
    bench.spine = _SpineThatHoldsAfterTheEnable(bench.harness.scheduler, bench.log)

    with pytest.raises(TorqueEngageSequenceError, match="after 0xFC"):
        _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    # Torque did come on — the refusal is about the frame behind it, not about reaching 0xFC.
    assert _left_bus(bench).enabled_motors == [list(fitted_motor_names(spatula_build()))]


def test_a_bus_that_answers_no_position_for_a_fitted_motor_is_refused(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    # A fitted joint that said nothing must not read as zero degrees. The arm hangs at the URDF
    # zero, so a substituted 0.0 is a hold target at the horizontal for that joint.
    unread = MOTOR_ORDER[3]
    bench = _Rig(tmp_path, unanswered=(unread,))

    with pytest.raises(FittedMotorMismatchError, match=unread):
        _engage(bench.build(), SIDES[0], passing_preflight, passing_manifest)

    assert _left_bus(bench).enabled_motors == []


def test_the_read_refuses_an_id_the_fitted_tool_does_not_carry(
    tmp_path: Path,
) -> None:
    bench = _Rig(tmp_path)
    bus = bench.build().for_side(SIDES[0])
    fitted = spatula_build().motor_send_ids

    with pytest.raises(FittedMotorMismatchError, match="ERROR-PASSIVE"):
        bus.read_present_pose((*fitted, GRIPPER_SEND_ID))

    assert _left_bus(bench).read_motors == []


def test_the_enable_refuses_without_a_present_pose_read(tmp_path: Path) -> None:
    bench = _Rig(tmp_path)
    bus = bench.build().for_side(SIDES[0])
    hold = build_present_pose_hold(
        tuple(deg_to_rad(angle) for angle in _present_deg(LEFT_BASE_DEG))
    )

    with pytest.raises(TorqueEngageSequenceError, match="no present pose"):
        bus.enable_torque(spatula_build().motor_send_ids, hold)

    assert _left_bus(bench).enabled_motors == []


def test_the_enable_refuses_a_frame_that_does_not_hold_the_pose_that_was_read(
    tmp_path: Path,
) -> None:
    bench = _Rig(tmp_path)
    bus = bench.build().for_side(SIDES[0])
    fitted = spatula_build().motor_send_ids
    present = bus.read_present_pose(fitted)
    drifted = build_present_pose_hold(tuple(Rad(angle.value + DRIFT_RAD) for angle in present))

    with pytest.raises(TorqueEngageSequenceError, match="is not the present pose"):
        bus.enable_torque(fitted, drifted)

    assert _left_bus(bench).enabled_motors == []


def test_the_enable_refuses_a_limp_frame(tmp_path: Path) -> None:
    # kp is the difference between a hold and a drop on an arm with no brake.
    bench = _Rig(tmp_path)
    bus = bench.build().for_side(SIDES[0])
    fitted = spatula_build().motor_send_ids
    present = bus.read_present_pose(fitted)
    limp = tuple(replace(command, kp=LIMP_KP) for command in build_present_pose_hold(present))

    with pytest.raises(SafeHoldViolationError):
        bus.enable_torque(fitted, limp)

    assert _left_bus(bench).enabled_motors == []


# --- The disengage ---


def test_the_drop_addresses_only_the_fitted_motors(
    tmp_path: Path,
    calibrated: None,
    passing_preflight: PreflightReport,
    passing_manifest: TorqueOnManifest,
) -> None:
    bench = _Rig(tmp_path)
    session = GuardedTorqueOn(
        bench.build().for_side(SIDES[0]), spatula_build(), passing_preflight, passing_manifest
    )
    session.engage()

    assert session.disengage(arm_supported=True) == spatula_build().motor_send_ids
    assert _left_bus(bench).dropped_motors == [list(fitted_motor_names(spatula_build()))]


def test_the_drop_refuses_an_id_the_fitted_tool_does_not_carry(tmp_path: Path) -> None:
    # Refusing here cannot strand an operator: a session drops its own fitted set, so this fires
    # only for a caller that named a motor the arm does not have.
    bench = _Rig(tmp_path)
    bus = bench.build().for_side(SIDES[0])

    with pytest.raises(FittedMotorMismatchError):
        bus.drop_torque((GRIPPER_SEND_ID,))

    assert _left_bus(bench).dropped_motors == []


# --- Assembly-time refusals ---


def test_a_pair_whose_arms_sit_in_the_wrong_slots_is_refused(tmp_path: Path) -> None:
    # The publisher keys each half on the arm's own side and assembles in the declared order, so
    # an arm in the wrong slot sends each arm the other one's angles — and both arms move.
    bench = _Rig(tmp_path, swap_arms=True)

    with pytest.raises(EngageBusUnassembledError, match="reports side"):
        bench.build()


def test_a_missing_side_is_refused(tmp_path: Path) -> None:
    bench = _Rig(tmp_path)
    with pytest.raises(EngageBusUnassembledError, match="carries arms"):
        build_engage_bus(
            spine=bench.spine,
            pair=bench.pair,
            buses={SIDES[0]: bench.buses[SIDES[0]]},
            end_effectors=_spatula_rig(),
        )


def test_a_fitted_motor_the_bus_does_not_register_is_refused(tmp_path: Path) -> None:
    # The rig record and the bus disagreeing about what is bolted on is the case where the engage
    # would address a motor the bus cannot even name.
    bench = _Rig(tmp_path)
    absent = fitted_motor_names(spatula_build())[-1]
    _left_bus(bench).motors = [motor for motor in MOTOR_ORDER if motor != absent]

    with pytest.raises(EngageBusUnassembledError, match="not registered"):
        bench.build()


def test_a_side_the_rig_does_not_carry_is_refused(tmp_path: Path) -> None:
    rig = _Rig(tmp_path).build()
    with pytest.raises(EngageBusUnassembledError, match="unknown side"):
        rig.for_side("middle")


def test_the_send_id_map_is_the_one_the_arms_bus_registers(tmp_path: Path) -> None:
    """The rig crosses names to ids; a map that drifts from the bus addresses another joint.

    Read off a real arm's own bus rather than off the config default, because the registration is
    what a frame is addressed by. Nothing at runtime compares the two, so a re-ordered
    `motor_config` upstream would leave the engage enabling joint_4 while holding joint_3's angle.
    """
    arm = OaOpenArmFollower(
        OaOpenArmFollowerConfig(side=Side.LEFT, id="wp105_ids", calibration_dir=tmp_path)
    )
    registered = {motor: definition.id for motor, definition in arm.bus.motors.items()}

    assert registered == SEND_ID_BY_MOTOR


# --- The deferred hardware acceptance, and proof its judgment bites ---


def _synthetic_capture(
    drift_rad: float = 0.0,
    kp: float = CAPTURED_KP,
    declares_absent_motor: bool = False,
) -> dict[str, Any]:
    """One capture record carrying a rig-engage block, in the schema the real one uses.

    Args:
        drift_rad: How far the emitted frame targets away from the reported pose.
        kp: The stiffness the emitted frame carried.
        declares_absent_motor: Whether the engage addressed `0x08` — self-consistently, the way
            a bus that really polled it writes.

    Returns:
        (dict[str, Any]) The capture record.
    """
    send_ids = list(spatula_build().motor_send_ids)
    if declares_absent_motor:
        send_ids.append(GRIPPER_SEND_ID)
    present = [
        deg_to_rad(Deg(LEFT_BASE_DEG + JOINT_STEP_DEG * index)).value
        for index in range(len(send_ids))
    ]
    return {
        ENGAGE_BLOCK: {
            SEND_IDS_KEY: send_ids,
            PRESENT_KEY: present,
            FRAME_KEY: [
                {
                    "kp": kp,
                    "kd": CAPTURED_KD,
                    "q": angle + drift_rad,
                    "dq": CAPTURED_DQ_RAD_S,
                    "tau": CAPTURED_TAU_NM,
                }
                for angle in present
            ],
        }
    }


def read_rig_engage(
    capture: dict[str, Any],
) -> tuple[tuple[int, ...], tuple[Rad, ...], tuple[ExecutedMitCommand, ...]]:
    """Read the ids, the reported pose and the emitted frame out of one capture record.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple) The ids the engage addressed, the pose the arm reported, and the fitted slice of
        the frame the single writer emitted.

    Raises:
        RigEngageMissingError: If the record carries no rig-engage block, or the block is missing
            any of the three.
    """
    block = capture.get(ENGAGE_BLOCK)
    required = (SEND_IDS_KEY, PRESENT_KEY, FRAME_KEY)
    if not isinstance(block, dict) or any(key not in block for key in required):
        raise RigEngageMissingError(
            f"the capture carries no {ENGAGE_BLOCK!r} block with {list(required)}; what the "
            "engage put on the bus is the whole measurement, and a capture without it answers "
            "nothing"
        )
    send_ids = tuple(int(send_id) for send_id in block[SEND_IDS_KEY])
    present = tuple(Rad(float(angle)) for angle in block[PRESENT_KEY])
    frame = tuple(
        ExecutedMitCommand(
            kp=float(command["kp"]),
            kd=float(command["kd"]),
            q=Rad(float(command["q"])),
            dq=RadPerSec(float(command["dq"])),
            tau=Nm(float(command["tau"])),
        )
        for command in block[FRAME_KEY]
    )
    return send_ids, present, frame


def judge_rig_engage(capture: dict[str, Any]) -> None:
    """Run the production judgments over one capture's rig-engage record.

    Args:
        capture: One parsed capture record.

    Raises:
        RigEngageMissingError: If the record carries no rig-engage block.
        FittedMotorMismatchError: If the engage addressed anything but the fitted motor set.
        SafeHoldViolationError: If the emitted frame commanded no restoring stiffness.
        TorqueEngageSequenceError: If the emitted frame left the reported pose.
    """
    send_ids, present, frame = read_rig_engage(capture)
    assert_capture_addressed_fitted_motors(send_ids, spatula_build().motor_send_ids)
    assert_safe_hold(frame)
    assert_targets_are_present_pose(frame, present)


def _capture_dir(root: Path, capture: dict[str, Any]) -> dict[str, Any]:
    """Write one capture record and read it back, the way the hook reads a real one."""
    path = root / "host.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    return dict(json.loads(path.read_text(encoding="utf-8")))


def test_an_engage_frame_that_left_the_reported_pose_is_flagged(tmp_path: Path) -> None:
    with pytest.raises(TorqueEngageSequenceError):
        judge_rig_engage(_capture_dir(tmp_path, _synthetic_capture(drift_rad=DRIFT_RAD)))


def test_a_limp_engage_frame_is_flagged(tmp_path: Path) -> None:
    with pytest.raises(SafeHoldViolationError):
        judge_rig_engage(_capture_dir(tmp_path, _synthetic_capture(kp=LIMP_KP)))


def test_an_engage_that_addressed_the_absent_motor_is_flagged(tmp_path: Path) -> None:
    # Eight ids and eight angles, agreeing with themselves. Nothing inside the record
    # contradicts anything else, so the refusal has to come from the fitted profile.
    with pytest.raises(FittedMotorMismatchError, match="fitted tool carries"):
        judge_rig_engage(_capture_dir(tmp_path, _synthetic_capture(declares_absent_motor=True)))


def test_a_correct_engage_capture_passes(tmp_path: Path) -> None:
    judge_rig_engage(_capture_dir(tmp_path, _synthetic_capture()))


def test_a_capture_with_no_rig_engage_block_fails(tmp_path: Path) -> None:
    # Silence is the failing side: a capture that never recorded the frame answers nothing.
    with pytest.raises(RigEngageMissingError):
        judge_rig_engage(_capture_dir(tmp_path, {"host_id": "synthetic-host"}))


@pytest.mark.skipif(_REAL_FIXTURE is None, reason=_SKIP_REASON)
def test_deferred_real_rig_engage_holds_the_fitted_motors() -> None:
    # Everything above runs on a fake CAN backend, so no frame here has been on a bus. This is
    # where the real one is judged, by the same production rules the synthetic captures prove
    # bite: the fitted set from the profile, the stiffness from `assert_safe_hold`, and the
    # angles from `assert_targets_are_present_pose`.
    assert _REAL_FIXTURE is not None
    for path in sorted(_REAL_FIXTURE.glob("*.json")):
        judge_rig_engage(json.loads(path.read_text(encoding="utf-8")))
