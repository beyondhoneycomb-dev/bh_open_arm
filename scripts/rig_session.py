"""The rig as the engage bus and the single writer address it: two channels, one write path.

`backend.torque_bringup.rig.build_engage_bus` borrows four things and builds none of them, for
two reasons stated in its own docstring: that package has to stay importable where `lerobot` is
absent, and the symbol that cuts torque may not appear in the tree that turns it on. Three of
the four are assembled here.

It sits beside the operator session rather than in the follower package because the follower
package claims its files by name in the plan corpus — a new file there is a file no work package
owns (CI-02b) — and because the one thing that drives this is `torque_session.py`. Nothing else
imports it, and a second importer would be a second writer on the two channels.

**Which channel is which arm is read, never derived.** Both arms answer on send `0x01–0x08`
(`03` §2.1), so nothing on the bus tells left from right, and the adapter has been observed at
two different USB port paths. `resolve_arm_interfaces` reads the operator's persisted answer
through `ops.hw.canbind`; the follower's own `PORT_BY_SIDE` default is a placeholder and is
overridden here on every arm.

**`drop_torque` is a rename and that is the whole reason it exists.** The bus calls the torque
cut `disable_torque`, and `backend.torque_bringup.stop_path` scans its own package for that
symbol as a precondition of engaging. So the name crosses here, on the far side of the
protocol, and the engage tree keeps an absolute scan instead of an exemption list.

**Only the fitted motors are addressed, on every call including the write.** The bimanual
emission is `BIMANUAL_BATCH_WIDTH` slots wide because the action layout is eight per arm; the
fitted spatula build puts a motor behind seven of them. A frame addressed to `0x08` is not an
error return — nobody ACKs it, the transmit error counter climbs, and the controller falls to
ERROR-PASSIVE, which degrades the seven joints that are present. `ArmWriteSlots` is where the
unfitted slots are marked so the writer can leave them alone.

**The cached hold is the pose the arms are in, read at assembly with torque off.** A tick that
finds the mailbox empty, stale or latched emits the scheduler's cached hold frame, and a
scheduler stood up on zeros would command every joint to the URDF zero. On this rig that zero is
the arm hanging beside the torso — forward kinematics at q=0 puts the end effector at
z = 0.904 m, below both J4=pi/2 (1.120 m) and J2=pi/2 (1.340 m). So a zeros hold does not reach
outward; it drives the arm **down** into the hang, out of the hands of whoever is holding it up.
The hold the scheduler starts on is measured, not defaulted.

**A bus read is not a reading unless the motor answered.** `DamiaoMotorsBus` keeps a state cache
initialised to zero for every registered motor and returns an entry for every name asked for,
whether or not that motor replied; a drop reaches the caller as a `logging.WARNING` and nothing
else. So a silent motor reads as 0.0 deg with every field present, and 0.0 deg is the hang — the
one value that looks plausible on this arm. Left unfiltered it defeats every downstream guard at
once, because each of them compares that number to something derived from the same number.
`RigArmBus` is where the vendor's semantics are translated: a motor the bus did not hear from is
absent from the result, which is the shape the engage's own refusal already reads.

**The single writer is supplied by the caller and never built here.** `ActuationScheduler` takes
the one CAN handle, and this tree may not name it: `find_producer_can_access` treats a reference
to the write symbol outside `backend/actuation` as a producer reaching for the handle, and that
scan is what keeps the write path single. So the writer arrives as an already-built object and
is passed through.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lerobot.motors.damiao import DamiaoMotorsBus

from backend.actuation import (
    BIMANUAL_BATCH_WIDTH,
    AcceptedTargetPublisher,
    ActuationScheduler,
    ArmWriteSlots,
    Clock,
    LeaseManager,
    MailboxProducer,
    TargetMailbox,
    TickTrace,
    WallClock,
    is_cache_initialiser,
)
from backend.actuation.config import LEASE_DURATION_SEC
from backend.calibration.schema import MOTOR_ORDER
from backend.can.lock import LockManager
from backend.endeffector import SIDE_LEFT, SIDE_RIGHT, SIDES, RigEndEffectors
from backend.torque_bringup.rig import (
    POSITION_FIELD,
    AssembledRig,
    build_engage_bus,
    fitted_motor_names,
)
from contracts.plugin.config import Side
from contracts.units import Deg, Rad, deg_to_rad
from ops.hw.canbind import (
    ArmRole,
    BindingError,
    binding_path,
    check_binding,
    list_can_channels,
    load_binding,
)
from packages.lerobot_robot_openarm.config_oa import (
    BiOaOpenArmFollowerConfig,
    OaOpenArmFollowerConfig,
)
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BiOaOpenArmFollower,
    OaOpenArmFollower,
)

# The follower role each arm side occupies in the persisted channel record. The leader roles
# exist in that record's vocabulary and this rig has none, so a role that is not one of these
# two is not something an engage would ever reach.
ARM_ROLE_BY_SIDE: dict[str, ArmRole] = {
    SIDE_LEFT: ArmRole.FOLLOWER_LEFT,
    SIDE_RIGHT: ArmRole.FOLLOWER_RIGHT,
}

# The `contracts.plugin.config` side each declared arm name resolves to. Two vocabularies for
# one fact, joined here rather than at each construction site.
PLUGIN_SIDE_BY_NAME: dict[str, Side] = {SIDE_LEFT: Side.LEFT, SIDE_RIGHT: Side.RIGHT}

# The producer identity the scheduler is stood up on. One operator session is one producer, and
# nothing swaps it: a swap is a mode transition, and this session has one mode.
SESSION_PRODUCER_ID = "torque-session"

# The bimanual pair's own config id. It never reaches a calibration file: both arms are injected
# already built, each with the instance id its own zero is stored under.
PAIR_ID = "torque-session-pair"

# What the cached hold carries for a slot the fitted tool puts no motor behind. The value never
# leaves: `ArmWriteSlots` marks the slot unfitted and the writer sends nothing for it. It is
# here because the scheduler's hold vector is the full frozen width and a slot cannot be absent
# from a tuple.
UNFITTED_SLOT_ANGLE_DEG = Deg(0.0)


class RigAssemblyError(RuntimeError):
    """Raised when the rig's write path cannot be assembled from what this host presents.

    Every case is refused before a socket opens or a frame goes out, so the arm is untouched:
    a channel the persisted binding does not resolve, a lock another process holds, or a bus
    that answered no position for a fitted motor. The alternative to raising is engaging
    against a channel nobody confirmed, and the two arms are indistinguishable on the bus.
    """


# The logger `DamiaoMotorsBus` reports a dropped read on, and the prefix its record carries. This
# is the only signal the bus emits: `sync_read_all_states` returns a cache entry for every motor
# asked for whether it answered or not, so the warning is what separates a reading from the zero
# the cache was initialised with. `test_rig_session` pins both against the installed library, so a
# release that renames the logger or reworded the record fails there instead of here, silently.
DAMIAO_BUS_LOGGER = "lerobot.motors.damiao.damiao"
PACKET_DROP_PREFIX = "Packet drop:"

# The cache-initialiser test and the field list it reads are `backend.actuation`'s, because the
# follower's per-command read needs the same test and the two must not be able to disagree about
# what counts as an answer.


class _DroppedMotorRecorder(logging.Handler):
    """Collects the motor names the bus reported a dropped read for during one poll.

    Ownership: attached to the bus's logger for the duration of a single read and removed after,
    so it never sees another caller's records. Not thread-safe by construction, which matches the
    single-threaded operator flow the engage runs in.
    """

    def __init__(self, motors: list[str]) -> None:
        """Watch for drops of the named motors only.

        Args:
            motors: The names this poll asked for; a record naming anything else is not ours.
        """
        super().__init__(level=logging.WARNING)
        self._watched = tuple(motors)
        self.dropped: set[str] = set()

    def emit(self, record: logging.LogRecord) -> None:
        """Record the drop this log line reports, if it reports one."""
        message = record.getMessage()
        if not message.startswith(PACKET_DROP_PREFIX):
            return
        self.dropped.update(name for name in self._watched if name in message)


class RigArmBus:
    """One arm's `DamiaoMotorsBus` in the shape the engage bus addresses it in.

    Ownership: borrows the bus handle the follower owns; opening and closing it stay the
    follower's. It adds no capability — the read and the enable are the bus's own, taking the
    motor names the caller passes rather than the bus's own construction list, because that
    list includes the id nothing answers on.

    Threading: the single-threaded operator flow, the same one `GuardedTorqueOn` runs in.
    """

    def __init__(self, bus: DamiaoMotorsBus) -> None:
        """Bind the adapter to one arm's bus.

        Args:
            bus: The arm's motors bus, already constructed. Registration is read here and the
                socket is not touched.
        """
        self._bus = bus
        # The live registration dict, aliased rather than copied: `build_engage_bus` asks it
        # whether a fitted motor is registered, and a copy taken here would answer for the bus
        # as it was at assembly rather than as it is.
        self.motors: Container[str] = bus.motors

    def sync_read_all_states(self, motors: list[str]) -> dict[str, dict[str, float]]:
        """Read the named motors' state, one entry per name **that answered**, in degrees.

        The bus does not distinguish the two. It keeps a cache initialised to zero for every
        registered motor and returns an entry for every name asked for, reporting a motor that
        said nothing as a `logging.WARNING` and returning the cached zero in the same shape a
        real reply has. Passed through, that zero is a present-pose reading of 0.0 deg, which on
        this arm is the hanging pose — plausible enough that every guard downstream accepts it,
        because each of them compares it to a value derived from it.

        So a motor that did not answer is dropped here. What reaches the engage is what the arm
        actually said, and the engage's own refusal on a missing fitted motor becomes reachable.

        Args:
            motors: The motor names to poll, and no others.

        Returns:
            (dict[str, dict[str, float]]) One state per name that answered this poll.
        """
        recorder = _DroppedMotorRecorder(motors)
        logger = logging.getLogger(DAMIAO_BUS_LOGGER)
        logger.addHandler(recorder)
        try:
            states = dict(self._bus.sync_read_all_states(motors))
        finally:
            logger.removeHandler(recorder)
        return {
            name: state
            for name, state in states.items()
            if name not in recorder.dropped and not is_cache_initialiser(state)
        }

    def enable_torque(self, motors: list[str]) -> None:
        """Enable torque (0xFC) on the named motors and no others.

        Args:
            motors: The motor names to energize.
        """
        self._bus.enable_torque(motors)

    def drop_torque(self, motors: list[str]) -> None:
        """Drop torque (0xFD) on the named motors and no others.

        The rename the engage tree needs. `backend.torque_bringup` scans itself for the bus's
        own name for this call as a precondition of engaging, so the symbol crosses here.

        Args:
            motors: The motor names to de-energize.
        """
        self._bus.disable_torque(motors)


@dataclass(frozen=True)
class RigSession:
    """One operator session's assembled write path, from the enforcement point to the channels.

    Ownership: owns the CAN channel locks and the two connected arms, and holds the scheduler
    that owns the single writer. `close` is what gives the locks and the sockets back, and it
    never cuts torque — a disconnect that disables torque drops a brakeless arm, and it would
    address the unfitted id while doing it.

    Attributes:
        pair: The bimanual enforcement surface both arms' commands go through.
        scheduler: The spine whose tick is the one CAN write.
        rig: The engage bus per arm, wired onto that spine.
        buses: Each arm's bus in the engage bus's shape.
        interfaces: Each arm's CAN interface, as the persisted binding resolved it.
        write_slots: What each arm's half of an emission addresses, arm-major.
        present_pose_deg: The pose each arm reported at assembly, fitted motors only.
        locks: The manager holding both channels' locks for as long as this session runs.
    """

    pair: BiOaOpenArmFollower
    scheduler: ActuationScheduler
    rig: AssembledRig
    buses: Mapping[str, RigArmBus]
    interfaces: Mapping[str, str]
    write_slots: tuple[ArmWriteSlots, ...]
    present_pose_deg: Mapping[str, tuple[Deg, ...]]
    locks: LockManager

    def close(self) -> None:
        """Close both channels and give the locks back, sending nothing on the way out.

        The bus's own disconnect disables torque first, over every motor it was constructed
        with. Both halves of that are wrong here: dropping torque on an arm nobody is
        supporting is a fall rather than a stop (`12` NFR-SAF-009), and the walk covers the
        unfitted id. Ending a hold is `GuardedTorqueOn.disengage`'s, and it takes the
        operator's declaration that the arm is supported.
        """
        for side in SIDES:
            bus = self.pair.left_arm.bus if side == SIDE_LEFT else self.pair.right_arm.bus
            if bus.is_connected:
                bus.disconnect(disable_torque=False)
        self.locks.release_all()


def resolve_arm_interfaces(config_directory: Path) -> dict[str, str]:
    """Return each arm's CAN interface, read from the operator's persisted channel record.

    Never derived from the interface name. `can0`/`can1` are not stable across a re-plug and
    the two arms are indistinguishable by CAN id (`03` §2.1), so the only answer is the one the
    operator settled by moving an arm and watching which channel's joints responded.

    Args:
        config_directory: Where the binding record lives.

    Returns:
        (dict[str, str]) One interface per declared arm side.

    Raises:
        RigAssemblyError: If the record cannot be read, or a follower role's channel is not
            present right now. Both are refusals: a binding that silently follows a
            renumbered bus is how the left arm's limits end up enforced against the right arm.
    """
    try:
        binding = load_binding(binding_path(config_directory))
        check = check_binding(binding, tuple(list_can_channels()))
    except (BindingError, OSError) as refusal:
        raise RigAssemblyError(
            f"the persisted CAN channel binding could not be read: {refusal}. The arms are "
            "indistinguishable on the bus, so there is nothing to fall back to"
        ) from refusal
    resolved: dict[str, str] = {}
    for side in SIDES:
        role = ARM_ROLE_BY_SIDE[side]
        interface = check.resolved.get(role)
        if interface is None:
            raise RigAssemblyError(
                f"{role.value} has no channel present right now; the adapter moved ports or a "
                "different one is plugged in. Re-identify which arm is on which channel — "
                "guessing from the interface name is what the binding record exists to prevent"
            )
        resolved[side] = interface
    return resolved


def arm_write_slots(
    buses: Mapping[str, DamiaoMotorsBus], end_effectors: RigEndEffectors
) -> tuple[ArmWriteSlots, ...]:
    """Describe what each arm's half of one emission addresses, in the frozen arm order.

    This is the single place a slot's index is joined to a motor name, and the join is a walk of
    `MOTOR_ORDER` itself rather than of the fitted set — so the half is in the frozen layout
    order whatever the tool leaves out, and the writer that consumes it can address the layout
    by index the way the rest of the actuation tree does. A build that filtered instead of
    masking would close the gap the unfitted slot leaves and shift every later joint by one.

    Args:
        buses: One raw bus per declared arm side.
        end_effectors: What each arm carries.

    Returns:
        (tuple[ArmWriteSlots, ...]) One entry per arm, arm-major, together covering every slot
        of a bimanual emission.

    Raises:
        RigAssemblyError: If the described slots do not cover the emission exactly. A writer
            given a narrower plan silently leaves joints uncommanded and a wider one indexes
            past the frame.
    """
    slots: list[ArmWriteSlots] = []
    for side in SIDES:
        fitted = set(fitted_motor_names(end_effectors.for_side(side)))
        slots.append(
            ArmWriteSlots(
                bus=buses[side],
                slot_names=tuple(name if name in fitted else None for name in MOTOR_ORDER),
            )
        )
    width = sum(len(arm.slot_names) for arm in slots)
    if width != BIMANUAL_BATCH_WIDTH:
        raise RigAssemblyError(
            f"the write plan covers {width} slots and one emission is {BIMANUAL_BATCH_WIDTH}; "
            "a plan narrower than the frame leaves joints uncommanded and a wider one is "
            "addressed past its end"
        )
    return tuple(slots)


def read_present_pose_deg(
    bus: RigArmBus, side: str, motor_names: tuple[str, ...]
) -> tuple[Deg, ...]:
    """Read one arm's present angle per fitted motor, in the order asked for.

    Args:
        bus: The arm's bus.
        side: Which arm, for the refusal message.
        motor_names: The fitted motors to poll, and no others.

    Returns:
        (tuple[Deg, ...]) One angle per named motor.

    Raises:
        RigAssemblyError: If the bus answered no position for a fitted motor. A substituted
            default would become the frame a lapsed tick holds on, and zero degrees on an arm
            hanging at the URDF zero is the horizontal.
    """
    states = bus.sync_read_all_states(list(motor_names))
    angles: list[Deg] = []
    for name in motor_names:
        state = states.get(name)
        if state is None or POSITION_FIELD not in state:
            raise RigAssemblyError(
                f"{side}: the bus answered no position for fitted motor {name}; the pose read "
                "here becomes the frame a tick with an empty mailbox holds on, and a "
                "substituted zero is the horizontal on an arm hanging at the URDF zero"
            )
        angles.append(Deg(float(state[POSITION_FIELD])))
    return tuple(angles)


def _initial_hold_rad(
    present_pose_deg: Mapping[str, tuple[Deg, ...]], end_effectors: RigEndEffectors
) -> tuple[Rad, ...]:
    """Build the cached hold the scheduler starts on: each arm where it is, arm-major.

    Args:
        present_pose_deg: Each arm's measured pose, fitted motors only.
        end_effectors: What each arm carries, which says which slots the pose fills.

    Returns:
        (tuple[Rad, ...]) The full-width hold vector, radians.
    """
    angles: list[Deg] = []
    for side in SIDES:
        fitted = fitted_motor_names(end_effectors.for_side(side))
        measured = dict(zip(fitted, present_pose_deg[side], strict=True))
        angles.extend(measured.get(name, UNFITTED_SLOT_ANGLE_DEG) for name in MOTOR_ORDER)
    return tuple(deg_to_rad(angle) for angle in angles)


def _build_arm(
    side: str,
    interface: str,
    robot_id: str,
    calibration_dir: Path,
    end_effectors: RigEndEffectors,
    clock: Clock,
    publisher: AcceptedTargetPublisher,
) -> OaOpenArmFollower:
    """Build one arm on the channel the binding resolved, holding the shared publisher.

    Args:
        side: Which arm.
        interface: The CAN interface this arm opens on.
        robot_id: The calibration instance id this arm loads its zero from.
        calibration_dir: Where that calibration lives.
        end_effectors: What each arm carries.
        clock: The one time base the watchdog, the publisher and the tick all read.
        publisher: The shared path from an accepted decision onto the scheduler's mailbox.

    Returns:
        (OaOpenArmFollower) The arm, with nothing opened.
    """
    return OaOpenArmFollower(
        OaOpenArmFollowerConfig(
            side=PLUGIN_SIDE_BY_NAME[side], id=robot_id, calibration_dir=calibration_dir
        ),
        end_effector=end_effectors.for_side(side),
        clock=clock,
        publisher=publisher,
        port=interface,
    )


def build_rig_session(
    make_can_writer: Callable[[tuple[ArmWriteSlots, ...]], Any],
    end_effectors: RigEndEffectors,
    calibration_dir: Path,
    robot_ids: Mapping[str, str],
    config_directory: Path,
) -> RigSession:
    """Assemble the whole write path over both arms, with nothing energized.

    The order is the safety. Both channel locks are taken before any socket opens (`01`
    FR-SYS-005); the arms come up holding nothing, though not off — `connect_readonly`
    commands no torque, but the handshake under it enables every fitted motor, so both arms
    are live from the moment this returns and have to be supported from here rather than from
    `engage`; the pose the scheduler will hold on is read from the arms rather than defaulted;
    the writer is built from the fitted slot plan, so no frame is addressed to a motor nobody
    answers on; and the deadman lease is renewed once at the end, because a first tick that
    reads an un-renewed lease emits a hold instead of the target that was just published.

    Args:
        make_can_writer: Builds the single CAN writer from the per-arm slot plan. Supplied
            rather than built here: this tree may not name the CAN handle, because a reference
            to the write symbol outside `backend/actuation` is what
            `find_producer_can_access` calls a producer reaching for it.
        end_effectors: What each arm carries; decides which motors are addressed at all.
        calibration_dir: Where each arm loads its zero from.
        robot_ids: The calibration instance id per arm side.
        config_directory: Where the persisted CAN channel binding lives.

    Returns:
        (RigSession) The assembled session. Torque is off on every motor.

    Raises:
        RigAssemblyError: If a channel does not resolve, if a lock is held elsewhere, if an arm
            fails to come up, or if a fitted motor answered no position.
        EngageBusUnassembledError: If the pair, the buses and the rig record disagree about
            what is bolted on or which arm is which.
    """
    interfaces = resolve_arm_interfaces(config_directory)
    clock: Clock = WallClock()
    mailbox = TargetMailbox()
    publisher = AcceptedTargetPublisher(mailbox, clock, SIDES)
    arms = {
        side: _build_arm(
            side=side,
            interface=interfaces[side],
            robot_id=robot_ids[side],
            calibration_dir=calibration_dir,
            end_effectors=end_effectors,
            clock=clock,
            publisher=publisher,
        )
        for side in SIDES
    }
    # Both arms are injected, so the pair's own config never builds one and its id reaches no
    # calibration file. Each arm already carries the instance id its zero is stored under.
    pair = BiOaOpenArmFollower(
        BiOaOpenArmFollowerConfig(id=PAIR_ID),
        left=arms[SIDE_LEFT],
        right=arms[SIDE_RIGHT],
    )

    locks = LockManager()
    acquired = locks.acquire_all([interfaces[side] for side in SIDES])
    if not acquired.ok:
        locks.release_all()
        raise RigAssemblyError(
            f"the writer lock on {acquired.blocked_iface} is held by {acquired.holder}; two "
            "writers on one channel is the exclusivity SocketCAN RAW cannot provide itself "
            "(01 FR-SYS-005), and the second one's frames are frames no filter judged"
        )
    try:
        pair.connect_readonly(locks)
        buses = {side: RigArmBus(arms[side].bus) for side in SIDES}
        present_pose_deg = {
            side: read_present_pose_deg(
                buses[side], side, fitted_motor_names(end_effectors.for_side(side))
            )
            for side in SIDES
        }
        write_slots = arm_write_slots({side: arms[side].bus for side in SIDES}, end_effectors)
        scheduler = ActuationScheduler(
            can_writer=make_can_writer(write_slots),
            mailbox=mailbox,
            clock=clock,
            lease=LeaseManager(LEASE_DURATION_SEC),
            initial_producer=MailboxProducer(SESSION_PRODUCER_ID, mailbox, clock),
            initial_hold_positions=_initial_hold_rad(present_pose_deg, end_effectors),
            trace=TickTrace(),
        )
        rig = build_engage_bus(spine=scheduler, pair=pair, buses=buses, end_effectors=end_effectors)
        # Live from here on. A first tick that reads an un-renewed lease emits the cached hold
        # rather than the target the engage just published, and on a brakeless arm the cached
        # frame is a pose from before this session.
        scheduler.renew_lease()
    except BaseException:
        for arm in arms.values():
            if arm.bus.is_connected:
                arm.bus.disconnect(disable_torque=False)
        locks.release_all()
        raise
    return RigSession(
        pair=pair,
        scheduler=scheduler,
        rig=rig,
        buses=buses,
        interfaces=interfaces,
        write_slots=write_slots,
        present_pose_deg=present_pose_deg,
        locks=locks,
    )
