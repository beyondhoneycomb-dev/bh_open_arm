"""The rig binding: the bus `GuardedTorqueOn` drives, wired to the assembled write path.

`GuardedTorqueOn` needs a `TorqueEngageBus`, and this is the one that reaches motors. Every
torque-bearing frame it causes leaves the way a commanded frame does: `send_action` filters, the
`AcceptedTargetPublisher` puts the accepted decision on the scheduler's mailbox, and one
scheduler tick performs the one CAN write. There is no second path, so the hold frame an engage
puts on the bus is judged by the same eight checks as every other frame.

Nothing here holds a CAN handle and nothing here builds one. The spine is borrowed, narrowed to
the two calls the engage makes on it (`EngageSpine`), and the arms are borrowed already wired to
the publisher whose mailbox that spine reads. Assembling those — two bus handles, the writer
that carries one 16-wide emission to both of them, the mailbox and the clock the halves share —
belongs to the tree that owns the CAN writer and to the tree that imports the robot stack.
Neither is this one: `backend.torque_bringup` has to stay importable where `lerobot` is absent,
and a `_mit_control_batch` here would put the CAN write symbol outside the single tree
`find_producer_can_access` exempts.

The torque drop sits on the injected bus for the mirrored reason. `find_disable_torque` runs
over this package as a precondition of engaging (`stop_path`), so the symbol that cuts torque
may not appear in the tree that turns it on. What a disengage *means* is
`GuardedTorqueOn.disengage`'s; what it sends is the bus's.

Every method takes the motor ids it may address and refuses anything else. The fitted build on
this bench is the spatula: seven motors, nothing on `0x08`. A frame addressed to an id nobody
answers on is not an error return — the transmit error counter climbs and the controller falls
to ERROR-PASSIVE, which degrades the seven joints that are present.

Torque comes on only after the write path has been shown to carry this session's own pose. The
published hold is ticked once while torque is still off: a MIT frame reaches a disabled motor
and moves nothing, and the emission it produces is what proves the publisher, the mailbox, the
scheduler and the writer are joined. A pair built without a publisher fails there, with nothing
energized — rather than after 0xFC, holding a brakeless arm with no frame behind it.

The frame that leaves is the enforcement point's decision, not the hold batch the sequence
built. The two agree while the arm is still, and when they do not it is because the arm moved
between the sequence's read and the gateway's own: the decision then holds where the arm is
now, and how far that is from where it was is already bounded by the SLEW and JERK stages. A
second bound here would be a threshold nobody measured standing in front of a guard that is
measured.
"""

from __future__ import annotations

from collections.abc import Container, Mapping
from dataclasses import dataclass
from typing import Protocol

from backend.actuation import Emission, EmissionLabel, GateResult
from backend.calibration.schema import MOTOR_ORDER
from backend.endeffector import (
    ARM_JOINT_SEND_IDS,
    GRIPPER_SEND_ID,
    SIDES,
    EndEffectorProfile,
    RigEndEffectors,
)
from backend.torque_bringup.hold import assert_safe_hold
from backend.torque_bringup.sequence import (
    FittedMotorMismatchError,
    TorqueEngageSequenceError,
    assert_targets_are_present_pose,
)
from contracts.action import ExecutedMitCommand
from contracts.teleop import POSITION_SUFFIX
from contracts.units import Deg, Rad, deg_to_rad

# The join between the frozen eight-slot action layout and the CAN send ids the bus registers.
# The fitted profile speaks ids and every bus call speaks names, so no frame can be addressed
# without crossing this map. `tests/wp105` pins it against the follower's own `motor_config`: a
# map that drifts from the bus registration addresses the wrong joint and says nothing.
SEND_ID_BY_MOTOR: dict[str, int] = dict(
    zip(MOTOR_ORDER, (*ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID), strict=True)
)
MOTOR_BY_SEND_ID: dict[int, str] = {send_id: motor for motor, send_id in SEND_ID_BY_MOTOR.items()}

# The bimanual action key format `BiOaOpenArmFollower.send_action` splits on. A key carrying
# neither side prefix reaches no arm at all, and the pair refuses it rather than dropping it.
SIDE_KEY_SEPARATOR = "_"

# The motor-state field a present-pose read takes its angle from, degrees (`sync_read_all_states`).
POSITION_FIELD = "position"


class EngageBusUnassembledError(RuntimeError):
    """Raised when the rig binding was handed parts that cannot engage an arm.

    Every case is a wiring fault that would otherwise surface as an energized arm with no hold
    frame behind it, or as a frame addressed to the wrong arm. Refused at assembly, where no
    motor is powered, rather than at the tick that would have shown it.
    """


class EngageSpine(Protocol):
    """The two calls the engage makes on the actuation spine, and nothing wider.

    Narrowed deliberately: an `ActuationScheduler` satisfies this, and holding it through this
    shape is what keeps the CAN writer — which the scheduler owns and never exposes — out of
    this package entirely.
    """

    def renew_lease(self) -> None:
        """Renew the deadman lease at the spine's own clock reading."""
        ...

    def tick(self) -> Emission:
        """Run one tick: decide, perform the one CAN write, and return what was written."""
        ...


class FittedArmBus(Protocol):
    """One arm's bus, addressed by fitted motor name on every call.

    A real `DamiaoMotorsBus` satisfies the read and the enable directly. The drop is named for
    what it does rather than for the upstream method, because the symbol that cuts torque may
    not appear in this package (`stop_path`); a one-method shim in the tree that owns the bus
    is what joins the two.
    """

    motors: Container[str]

    def sync_read_all_states(self, motors: list[str]) -> dict[str, dict[str, float]]:
        """Read the named motors' state, one entry per name, positions in degrees."""
        ...

    def enable_torque(self, motors: list[str]) -> None:
        """Enable torque (0xFC) on the named motors and no others."""
        ...

    def drop_torque(self, motors: list[str]) -> None:
        """Drop torque (0xFD) on the named motors and no others."""
        ...


class DecidingArm(Protocol):
    """One arm's enforcement record: which side it is, and what its gateway last decided."""

    @property
    def side(self) -> str:
        """The arm side, matching the publisher's declared side names."""
        ...

    @property
    def last_gate_result(self) -> GateResult | None:
        """The gateway decision from the most recent `send_action`, or None before the first."""
        ...


class CommandedPair(Protocol):
    """The bimanual pair's single enforcement surface, plus each arm's recorded decision.

    Structural so this package pulls in no robot stack. `BiOaOpenArmFollower` satisfies it; the
    engage commands the pair rather than an arm, because the mailbox slot is one bimanual target
    and a round that publishes half of it hands the writer a frame no decision produced.
    """

    left_arm: DecidingArm
    right_arm: DecidingArm

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        """Judge and command both arms; a slot left out of the action holds at its present angle."""
        ...


@dataclass(frozen=True)
class _PoseRead:
    """One present-pose read of one arm's fitted motors, as the bus reported it.

    Attributes:
        send_ids: The ids the read addressed, in the order the caller asked for.
        motor_names: The bus names those ids resolved to, same order.
        angles_deg: The reported angle per fitted motor, degrees, same order.
    """

    send_ids: tuple[int, ...]
    motor_names: tuple[str, ...]
    angles_deg: tuple[Deg, ...]

    @property
    def angles_rad(self) -> tuple[Rad, ...]:
        """The same angles in radians — the unit `TorqueEngageBus` speaks."""
        return tuple(deg_to_rad(angle) for angle in self.angles_deg)


def fitted_motor_names(profile: EndEffectorProfile) -> tuple[str, ...]:
    """Return the bus names of the motors a fitted tool actually carries.

    Args:
        profile: The tool fitted to one arm.

    Returns:
        (tuple[str, ...]) The motor names, in the profile's own id order.

    Raises:
        EngageBusUnassembledError: If the profile declares an id outside the frozen layout, so
            no bus name exists for it and the engage would address an id nothing maps to.
    """
    names: list[str] = []
    for send_id in profile.motor_send_ids:
        motor = MOTOR_BY_SEND_ID.get(send_id)
        if motor is None:
            known = ", ".join(f"{value:#04x}" for value in MOTOR_BY_SEND_ID)
            raise EngageBusUnassembledError(
                f"the fitted {profile.tool_id} tool declares send id {send_id:#04x}, which the "
                f"frozen motor layout does not name (it carries {known})"
            )
        names.append(motor)
    return tuple(names)


class AssembledEngageBus:
    """One arm's `TorqueEngageBus`, whose every frame leaves through the single writer.

    Ownership: holds this arm's bus handle and fitted profile, and borrows the pair and the
    spine — both shared with the other arm, because one bimanual target serves both. It owns no
    CAN handle: the frames it causes are written by the scheduler tick.

    Threading: the single-threaded operator flow `GuardedTorqueOn` runs in. The present-pose
    read and the enable that follows it are one ordered pair of calls on one arm; two engages
    driven concurrently would interleave their publishes into the one mailbox slot.
    """

    def __init__(
        self,
        side: str,
        bus: FittedArmBus,
        profile: EndEffectorProfile,
        pair: CommandedPair,
        spine: EngageSpine,
    ) -> None:
        """Bind one arm's engage bus to its hardware, its tool, and the shared write path.

        Args:
            side: Which arm this is, in the publisher's declared side names.
            bus: This arm's bus handle; every call it receives names its motors explicitly.
            profile: The tool fitted to this arm, which decides the addressed motor set.
            pair: The bimanual enforcement surface both arms' frames go through.
            spine: The actuation spine whose tick is the one CAN write.
        """
        self._side = side
        self._bus = bus
        self._profile = profile
        self._pair = pair
        self._spine = spine
        self._fitted_names = fitted_motor_names(profile)
        self._read: _PoseRead | None = None
        self._emitted: tuple[ExecutedMitCommand, ...] | None = None

    @property
    def side(self) -> str:
        """The arm this bus addresses.

        Returns:
            (str) The declared side name.
        """
        return self._side

    @property
    def last_emitted_frame(self) -> tuple[ExecutedMitCommand, ...] | None:
        """The frame the single writer last emitted for this arm's engage, or None.

        The audit's other half. `EngageResult` records the hold the sequence built and the pose
        it was built from, which is what the engage asked for; this is what actually went out,
        and the two are the same object only while the arm was still.

        Returns:
            (tuple[ExecutedMitCommand, ...] | None) The bimanual frame of the engage's tick.
        """
        return self._emitted

    def read_present_pose(self, send_ids: tuple[int, ...]) -> tuple[Rad, ...]:
        """Read the current angle of each named motor, in radians, in the given id order.

        Args:
            send_ids: The ids to read. Must be exactly this arm's fitted set.

        Returns:
            (tuple[Rad, ...]) One angle per named motor, in the order asked for.

        Raises:
            FittedMotorMismatchError: If the ids are not the fitted set, or the bus answered no
                position for a fitted motor.
        """
        self._refuse_unfitted(send_ids)
        names = tuple(MOTOR_BY_SEND_ID[send_id] for send_id in send_ids)
        # The explicit list is the point. `sync_read_all_states()` with no argument walks every
        # motor the bus was constructed with, which on a spatula build includes the id nothing
        # answers on — the same default that once made `set_zero` poll it.
        states = self._bus.sync_read_all_states(list(names))
        angles: list[Deg] = []
        for name in names:
            state = states.get(name)
            if state is None or POSITION_FIELD not in state:
                raise FittedMotorMismatchError(
                    f"{self._side}: the bus answered no position for fitted motor {name} "
                    f"({SEND_ID_BY_MOTOR[name]:#04x}). A substituted default would engage that "
                    "joint against an angle nobody read, and zero degrees on an arm hanging at "
                    "the URDF zero is the horizontal"
                )
            angles.append(Deg(float(state[POSITION_FIELD])))
        self._read = _PoseRead(send_ids=send_ids, motor_names=names, angles_deg=tuple(angles))
        return self._read.angles_rad

    def enable_torque(
        self, send_ids: tuple[int, ...], hold_batch: tuple[ExecutedMitCommand, ...]
    ) -> None:
        """Enable torque (0xFC) on the named motors holding the given present-pose frame.

        The enable and the first MIT frame are one call because a motor between the two holds
        nothing, and this arm has no brake. Before either happens the whole write path is driven
        once with torque still off, so a path that cannot carry the frame is found while nothing
        is energized.

        Args:
            send_ids: The ids to enable. Must be the ids the preceding read addressed.
            hold_batch: The present-pose hold frame, one command per fitted motor.

        Raises:
            TorqueEngageSequenceError: If no pose was read first, if the frame does not hold the
                pose that was read, or if what the writer emitted is not the decision the
                enforcement point reached.
            FittedMotorMismatchError: If the ids are not this arm's fitted set.
            SafeHoldViolationError: If the frame commands no restoring stiffness.
        """
        read = self._require_pose_read(send_ids)
        assert_safe_hold(hold_batch)
        assert_targets_are_present_pose(hold_batch, read.angles_rad)

        action = self._hold_action(read)
        decisions = self._command_pair(action)
        self._refuse_unauthorized_frame(
            self._tick(), decisions, "with torque still off, before 0xFC"
        )

        self._bus.enable_torque(list(read.motor_names))
        decisions = self._command_pair(action)
        emission = self._tick()
        self._emitted = emission.batch
        self._refuse_unauthorized_frame(emission, decisions, "as the first frame after 0xFC")

    def drop_torque(self, send_ids: tuple[int, ...]) -> None:
        """Drop torque (0xFD) on the named motors, ending the hold.

        Never refused for being un-engaged: `GuardedTorqueOn.disengage` is the operator's way out
        of a live arm, and a refusal there strands them. It is refused for addressing motors this
        arm does not carry, which is a different mistake and cannot be the one an operator ending
        a session made — the session passes its own fitted set.

        Args:
            send_ids: The ids to drop. Must be this arm's fitted set.

        Raises:
            FittedMotorMismatchError: If the ids are not this arm's fitted set.
        """
        self._refuse_unfitted(send_ids)
        names = [MOTOR_BY_SEND_ID[send_id] for send_id in send_ids]
        self._bus.drop_torque(names)

    def _refuse_unfitted(self, send_ids: tuple[int, ...]) -> None:
        """Refuse an id set that is not exactly what this arm carries.

        Raises:
            FittedMotorMismatchError: On any other set.
        """
        fitted = self._profile.motor_send_ids
        if send_ids == fitted:
            return
        addressed = ", ".join(f"{send_id:#04x}" for send_id in send_ids)
        carried = ", ".join(f"{send_id:#04x}" for send_id in fitted)
        raise FittedMotorMismatchError(
            f"{self._side}: the call addresses ({addressed}) but the fitted "
            f"{self._profile.tool_id} carries ({carried}); nobody answers on an id outside the "
            "fitted set, and the unanswered frames walk the controller to ERROR-PASSIVE and "
            "degrade the joints that are present"
        )

    def _require_pose_read(self, send_ids: tuple[int, ...]) -> _PoseRead:
        """Return the pose read this enable must hold at, refusing an unread one.

        The ids the enable names and the ids the read named are not compared, because they
        cannot differ: both calls go through the fitted-set refusal, which admits one set. A
        comparison here would be a check no input can fail.

        Raises:
            FittedMotorMismatchError: If the ids are not this arm's fitted set.
            TorqueEngageSequenceError: If nothing was read.
        """
        self._refuse_unfitted(send_ids)
        read = self._read
        if read is None:
            raise TorqueEngageSequenceError(
                f"{self._side}: 0xFC refused — no present pose has been read on this bus. Torque "
                "must come on holding where the arm already is, and there is no reading to hold"
            )
        return read

    def _hold_action(self, read: _PoseRead) -> dict[str, float]:
        """Build the bimanual action that asks this arm to hold the pose that was read.

        Only this arm's fitted joints are named. Every other slot — this arm's unfitted gripper
        slot and the whole other arm — is left out, and a slot left out holds at its own present
        angle, read by the enforcement point rather than transcribed here.

        Args:
            read: The pose this arm is to hold.

        Returns:
            (dict[str, float]) The action, keys `{side}_{motor}.pos` in degrees.
        """
        return {
            f"{self._side}{SIDE_KEY_SEPARATOR}{name}{POSITION_SUFFIX}": angle.value
            for name, angle in zip(read.motor_names, read.angles_deg, strict=True)
        }

    def _command_pair(self, action: dict[str, float]) -> tuple[GateResult, ...]:
        """Run one command through the pair and return both arms' decisions, in side order.

        Args:
            action: The bimanual position action.

        Returns:
            (tuple[GateResult, ...]) One decision per arm, left then right.

        Raises:
            TorqueEngageSequenceError: If an arm reached no decision, which means the command
                did not reach its gateway and nothing was judged.
        """
        self._pair.send_action(action)
        decisions: list[GateResult] = []
        for side, arm in zip(SIDES, (self._pair.left_arm, self._pair.right_arm), strict=True):
            decision = arm.last_gate_result
            if decision is None:
                raise TorqueEngageSequenceError(
                    f"the {side} arm recorded no decision for the engage command; its gateway "
                    "never judged the frame, so nothing about what would be sent is known"
                )
            decisions.append(decision)
        return tuple(decisions)

    def _tick(self) -> Emission:
        """Renew the deadman and run one tick — the one CAN write.

        The lease is renewed here because the tick that carries the engage must emit the target
        that was just published: an expired lease emits the spine's cached hold instead, which
        is a pose from before this engage and on a brakeless arm a jump to it.

        Returns:
            (Emission) What the writer emitted this tick.
        """
        self._spine.renew_lease()
        return self._spine.tick()

    def _refuse_unauthorized_frame(
        self, emission: Emission, decisions: tuple[GateResult, ...], moment: str
    ) -> None:
        """Refuse a frame that is not the decision the enforcement point just reached.

        This is what catches a mis-joined write path: a pair publishing into another mailbox, a
        round that never completed, a spine that clamped the vector or was holding a cached
        frame, or halves assembled in the other arm order. The comparison is exact because both
        sides cross degrees to radians through the one sanctioned conversion applied to the same
        value, so agreement is identity and any difference is a different frame.

        Args:
            emission: What the writer emitted.
            decisions: Both arms' decisions for the command that produced it, in side order.
            moment: Where in the engage this frame went out, for the refusal message.

        Raises:
            TorqueEngageSequenceError: If the emission is a hold rather than the published
                target, or its angles are not the accepted ones.
            SafeHoldViolationError: If the emitted frame commands no restoring stiffness.
        """
        if emission.label is not EmissionLabel.ACCEPTED_TARGET:
            raise TorqueEngageSequenceError(
                f"{self._side}: the frame emitted {moment} was {emission.label.value} "
                f"({emission.reason.value}), not the published hold. The write path did not "
                "carry this engage's target, so what reached the motors is a frame this engage "
                "never authorized"
            )
        assert_safe_hold(emission.batch)
        authorized = tuple(
            deg_to_rad(angle) for decision in decisions for angle in decision.accepted
        )
        emitted = tuple(command.q for command in emission.batch)
        if emitted != authorized:
            raise TorqueEngageSequenceError(
                f"{self._side}: the frame emitted {moment} is {len(emitted)} joints of "
                f"{[angle.value for angle in emitted]} rad while the enforcement point accepted "
                f"{[angle.value for angle in authorized]} rad; the frame on the bus is not the "
                "one the eight-check filter decided on"
            )


@dataclass(frozen=True)
class AssembledRig:
    """The rig's two engage buses and the spine that keeps their hold alive.

    Ownership: holds one `AssembledEngageBus` per arm and borrows the spine both share. The
    engage of one arm is one `GuardedTorqueOn` session over one of these; the pair is engaged by
    running two, and each one's frame carries the other arm's present-pose hold with it because
    the mailbox slot is one bimanual target.

    Attributes:
        left: The left arm's engage bus.
        right: The right arm's engage bus.
        spine: The actuation spine whose tick is the single CAN write.
    """

    left: AssembledEngageBus
    right: AssembledEngageBus
    spine: EngageSpine

    def for_side(self, side: str) -> AssembledEngageBus:
        """Return one arm's engage bus.

        Args:
            side: `left` or `right`, the CTR-ACT arm order.

        Returns:
            (AssembledEngageBus) That arm's bus.

        Raises:
            EngageBusUnassembledError: On any other name — a typo must not resolve to the arm
                that happens to be first.
        """
        for name, bus in zip(SIDES, (self.left, self.right), strict=True):
            if name == side:
                return bus
        raise EngageBusUnassembledError(f"unknown side {side!r}; the rig carries {SIDES}")

    def maintain_hold(self) -> Emission:
        """Re-send the hold, once, and return what went out.

        An engage puts one frame on the bus; the arm stays up because the frame keeps being
        sent. The caller drives this inside the RID-9 no-send margin (`12` NFR-SAF-007,
        `RID9_NO_SEND_MARGIN_SEC`) for as long as the arm is energized.

        The deadman lease is deliberately not renewed here. Renewing it from the maintenance
        loop is a deadman nobody is holding, and a lapsed lease emits the same position hold on
        the same cached frame, which is the outcome that keeps a brakeless arm up either way.

        Returns:
            (Emission) What the writer emitted this tick.
        """
        return self.spine.tick()


def build_engage_bus(
    spine: EngageSpine,
    pair: CommandedPair,
    buses: Mapping[str, FittedArmBus],
    end_effectors: RigEndEffectors,
) -> AssembledRig:
    """Wire the rig's guarded torque-ON onto the assembled write path.

    The parts are borrowed rather than built. The spine is whatever owns the single CAN writer;
    the pair is the enforcement surface, already holding the publisher whose mailbox that spine
    reads; the buses are the two arms' handles; the end-effector record says which motors each
    arm carries. Assembling those four is the job of the tree that imports the robot stack, and
    the write path they form is verified on this session's own pose before any 0xFC leaves.

    Args:
        spine: The actuation spine whose tick performs the one CAN write.
        pair: The bimanual follower, whose arms must report the declared sides in the frozen
            arm-major order.
        buses: One bus handle per declared side.
        end_effectors: What each arm carries, as the rig record stores it.

    Returns:
        (AssembledRig) One engage bus per arm, plus the spine that maintains their hold.

    Raises:
        EngageBusUnassembledError: If a declared side has no bus, if `buses` names a side the
            rig does not have, if an arm reports a side other than the one whose slot it
            occupies, if a fitted tool declares no motors, or if a fitted motor is not
            registered on that arm's bus.
    """
    arms = (pair.left_arm, pair.right_arm)
    if set(buses) != set(SIDES):
        raise EngageBusUnassembledError(
            f"the rig was given buses for {sorted(buses)} and carries arms {list(SIDES)}; a "
            "missing side has no handle to read or enable, and a side that is not an arm names "
            "a bus no engage would ever reach"
        )
    built: list[AssembledEngageBus] = []
    for side, arm in zip(SIDES, arms, strict=True):
        # The publisher keys each half on the arm's own `side` and assembles in the declared
        # order, so an arm sitting in the wrong slot publishes its angles into the other arm's
        # joints and both arms move — to each other's targets.
        if arm.side != side:
            raise EngageBusUnassembledError(
                f"the arm in the {side} slot reports side {arm.side!r}; the bimanual frame is "
                "assembled in the declared arm order, so this pair would send each arm the "
                "other one's angles"
            )
        profile = end_effectors.for_side(side)
        if not profile.motor_send_ids:
            raise EngageBusUnassembledError(
                f"the {side} arm's fitted {profile.tool_id} declares no motors; there is nothing "
                "to engage and a zero-width frame would be sent to the bus"
            )
        bus = buses[side]
        for name in fitted_motor_names(profile):
            if name not in bus.motors:
                raise EngageBusUnassembledError(
                    f"the {side} arm's fitted {profile.tool_id} carries motor {name} "
                    f"({SEND_ID_BY_MOTOR[name]:#04x}), which is not registered on that arm's "
                    "bus; the rig record and the bus disagree about what is bolted on, and the "
                    "engage would address a motor the bus cannot name"
                )
        built.append(
            AssembledEngageBus(side=side, bus=bus, profile=profile, pair=pair, spine=spine)
        )
    left, right = built
    return AssembledRig(left=left, right=right, spine=spine)
