"""Which arm the served process holds — the host end of the dummy↔real swap (`FR-SYS-003`).

`01` FR-SYS-003 makes the choice of backend a config token rather than a source edit, and
`backend.actuation.ArmSession` is built to match: it takes one read per arm side and knows
nothing about what is behind them. This module is where a name becomes those reads.

The default is no arm at all, and that is the load-bearing decision here. A server that
defaulted to the dummy would publish synthetic joint angles onto the board an operator reads,
under the same API a real reading arrives through, with nothing on the screen to separate them.
`FR-SIM-098`'s dummy exists so the loop can be exercised with no bus — not so the process has
something to show when it has no arm.

The real backend opens the bus, and what that costs is stated here rather than left to be
discovered: `DamiaoMotorsBus.connect()` handshakes every registered motor with `CAN_CMD_ENABLE`,
so `--arm real` leaves fourteen motors ENERGIZED for as long as the server runs. They hold
nothing — kp, kd and tau stay zero and nothing on this path commands otherwise — but a brakeless
arm that is enabled is one frame from moving, so an operator has to be able to support it before
this name is used. It reads and never writes: `ArmSession` has no send path, and `FR-GUI-065`'s
stop is still `STOP_HOLD_SENDER`'s to wire.

What it refuses rather than guesses is which arm is on which channel. The two arms answer on the
same CAN ids (`03` §2.1), so the operator's persisted identification is the only evidence, and a
fallback to "the first CAN interface" is indistinguishable from the right answer until the arm
moves.

Assembling the process is what this tree does, which is why the import of a `packages/` plugin
lives here rather than in `backend/actuation`: the session takes callables, and choosing what is
behind them is the host's job.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.actuation.clock import Clock
from backend.actuation.guard import GuardSample
from backend.actuation.session import ArmFrame, ArmSession
from backend.calibration.schema import MOTOR_ORDER
from backend.can.lock import LockManager
from backend.config.store import default_config_directory
from contracts.plugin.config import Side
from contracts.prim.schema import ARM_SIDES
from contracts.units import Deg, Nm
from ops.hw.canbind.binding import ArmRole, BindingError, binding_path, load_binding
from ops.hw.canbind.discovery import list_can_channels
from packages.lerobot_robot_openarm.config_oa import BiOaOpenArmFollowerConfig
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BiOaOpenArmFollower,
    OaOpenArmFollower,
)
from packages.lerobot_robot_openarm_dummy.config import DummyRobotConfig
from packages.lerobot_robot_openarm_dummy.robot import DummyOpenArmRobot

ARM_BACKEND_NONE = "none"
ARM_BACKEND_DUMMY = "dummy"
ARM_BACKEND_REAL = "real"

# The names `oa-serve --arm` accepts, in the order it lists them. The parser reads this rather
# than a second copy, so a name the CLI offers cannot be one `build_arm_backend` refuses.
ARM_BACKENDS = (ARM_BACKEND_NONE, ARM_BACKEND_DUMMY, ARM_BACKEND_REAL)

# The backends whose board readings came from an arm. The startup report branches on this, and it
# is a set rather than `!= ARM_BACKEND_DUMMY` so a fourth name has to state which side it is on
# instead of inheriting "real" by not being the dummy.
ARM_BACKENDS_ON_HARDWARE = (ARM_BACKEND_REAL,)

# The LeRobot instance id the dummy follower is constructed under. It reaches no filesystem and
# no bus; it exists because `RobotConfig` carries the field.
DUMMY_ROBOT_ID = "oa-serve-dummy"

# The instance id the hardware pair is constructed under. Unlike the dummy's this one reaches the
# filesystem: the per-arm ids derive from it and name the calibration records the zero lives in.
REAL_ROBOT_ID = "oa-serve"

# Which persisted role answers for which side. The binding file is written by
# `canbind_session`, whose identification is the operator physically moving one arm.
ROLE_BY_SIDE = {Side.LEFT.value: ArmRole.FOLLOWER_LEFT, Side.RIGHT.value: ArmRole.FOLLOWER_RIGHT}

# The observation channel suffixes one arm's board is assembled from. Velocity is in the
# follower's schema and not on the board: `ArmState` pairs a pose with a torque because a
# residual is computed across those two, and a channel nothing reads is a field to keep true.
POSITION_SUFFIX = ".pos"
TORQUE_SUFFIX = ".torque"


class DummySideReader:
    """One arm side's read, over a CAN-free bimanual follower.

    Ownership: holds the follower (not owned — one follower serves both sides) and the side it
    reports. Calling it polls the follower once and slices that observation down to this side.

    A rig is polled one side at a time here, and that is the shape the bench has rather than a
    limitation of the double: `can0` and `can1` are separate buses read in sequence, so two arms
    never answer in the same instant. The dummy advances its synthetic step per poll, which
    reproduces that separation instead of hiding it.
    """

    def __init__(self, robot: DummyOpenArmRobot, side: str) -> None:
        """Bind the read to one follower and one side.

        Args:
            robot: The connected CAN-free follower both sides are polled from.
            side: The arm side this read reports, as named in `ARM_SIDES`.
        """
        self._robot = robot
        self._side = side

    def __call__(self) -> ArmFrame:
        """Poll once and answer this side's pose, torque and guard sample.

        The guard sample is healthy because every channel the guard judges is a property of a
        bus: a poll that answered, a read with no drops, a lock this process holds. A CAN-free
        follower has none of those to fail, so reporting anything else would be inventing a
        fault the deployment cannot have.

        Returns:
            (ArmFrame) The pose, the torque and the guard sample from this poll.
        """
        observation = self._robot.get_observation()
        return (
            tuple(
                Deg(float(observation[f"{self._side}_{motor}{POSITION_SUFFIX}"]))
                for motor in MOTOR_ORDER
            ),
            tuple(
                Nm(float(observation[f"{self._side}_{motor}{TORQUE_SUFFIX}"]))
                for motor in MOTOR_ORDER
            ),
            GuardSample.healthy(),
        )


class RealSideReader:
    """One arm side's read, over the hardware follower for that side.

    Ownership: holds the follower for this side (not owned — the pair owns both, and the pair is
    what gets disconnected). Calling it is one CAN round trip on that side's channel.

    It reads `read_frame` rather than assembling channels out of `get_observation`, because the
    guard sample is not a channel and the sample is the whole point on hardware: every field it
    carries — a motor that answered, a read with no drops, a lock still held — is something this
    bus does fail at, and the deadman and the latch act on those.

    Threading: `ArmSessionRunner` is the only thread that calls this, which is also what makes
    the board's lock-free publish safe. A second caller on this bus would take the other's
    replies and read the missing ones as absent motors, so a command path added later has to
    reach the bus through this same loop rather than beside it.
    """

    def __init__(self, arm: OaOpenArmFollower) -> None:
        """Bind the read to one connected arm.

        Args:
            arm: The connected follower for this side.
        """
        self._arm = arm

    def __call__(self) -> ArmFrame:
        """Poll once and answer this side's pose, torque and guard sample.

        Returns:
            (ArmFrame) The pose, the torque and the guard sample from this poll.
        """
        return self._arm.read_frame()


class RealBackendTeardown:
    """Closes what `--arm real` opened: torque off, buses closed, channel locks released.

    Ownership: owns the pair and the lock manager for the life of the served process.

    This exists because the alternative is leaving the motors to the comm-loss timeout. That
    timeout is real and it does drop them, but it is the hardware's backstop for a process that
    died — and a shutdown this process chose is not that. Disconnecting is also what frees the
    channel locks in an order the next session can read: torque off first, then the socket, then
    the lock, so nothing else can open the bus while the motors are still enabled.
    """

    def __init__(self, robot: BiOaOpenArmFollower, lock_manager: LockManager) -> None:
        """Bind the teardown to the pair and the locks one build opened.

        Args:
            robot: The connected bimanual follower.
            lock_manager: The manager holding both arms' interface locks.
        """
        self._robot = robot
        self._lock_manager = lock_manager

    def __call__(self) -> None:
        """Disconnect the pair, then release the locks — locks last, and released either way.

        `disconnect` disables torque on the way out (`bus.disconnect(True)`). If it raises, the
        locks are still released: a held lock outliving the process that held it is what makes
        the next session refuse with a holder that is gone.
        """
        try:
            self._robot.disconnect()
        finally:
            self._lock_manager.release_all()


class DummyBackendTeardown:
    """Disconnects the CAN-free double.

    Nothing here is on a bus, so this frees no hardware. It runs anyway because the dummy exists
    to exercise the wiring, and a shutdown path only the real backend takes is a shutdown path
    nothing tests.
    """

    def __init__(self, robot: DummyOpenArmRobot) -> None:
        """Bind the teardown to the connected double.

        Args:
            robot: The connected dummy follower.
        """
        self._robot = robot

    def __call__(self) -> None:
        """Disconnect the double."""
        self._robot.disconnect()


class NoBackendTeardown:
    """Closes nothing, for the process that holds no arm."""

    def __call__(self) -> None:
        """Do nothing. `--arm none` opened nothing."""


@dataclass(frozen=True)
class ArmBackend:
    """A built arm backend: the session to tick, and what closing it takes.

    The two travel together because they are one decision. `build_arm_backend` opens a bus for
    one of its names, and a caller handed only the session has nothing to close — which on
    hardware means a served process that exits with fourteen motors still enabled and both
    channel locks still held.

    Attributes:
        session: The session to tick, or None when this process holds no arm.
        close: Releases whatever the build opened. Idempotent is not promised; call it once,
            from the same `finally` that stops the tick.
    """

    session: ArmSession | None
    close: Callable[[], None]


class ArmChannelsUnavailableError(RuntimeError):
    """The hardware backend could not be given a channel per arm."""


def resolve_arm_channels() -> dict[str, str]:
    """Answer which kernel interface each arm side is on, from the operator's record.

    The binding is keyed on the adapter's physical position plus the channel index, so `canN`
    renumbering across a reboot does not move an arm. Both sides must resolve: a pair built with
    one arm on a guessed channel is a pair whose left commands could reach its right.

    Returns:
        (dict) Side name to the kernel interface to open, for both sides.

    Raises:
        ArmChannelsUnavailableError: If the record is missing, unreadable, or names a channel
            that is not present now. Refused rather than defaulted, because the two arms are
            indistinguishable on the bus (`03` §2.1) and a wrong guess is only visible once the
            arm moves.
    """
    directory = default_config_directory()
    present = tuple(list_can_channels())
    try:
        binding = load_binding(binding_path(directory))
        return {side: binding.interface_for(ROLE_BY_SIDE[side], present) for side in ARM_SIDES}
    except (OSError, ValueError, KeyError, BindingError) as unresolved:
        raise ArmChannelsUnavailableError(
            f"no usable CAN channel record under {directory}: {unresolved}. "
            "Run `scripts/canbind_session.sh` to identify which arm is on which channel; "
            "the arms answer on the same CAN ids, so this cannot be guessed."
        ) from unresolved


def _build_real_backend(clock: Clock) -> ArmBackend:
    """Open both arms' buses torque-uncommanded and hand back the session over them.

    The motors are ENERGIZED once this returns, by the vendor bus's connect handshake. They hold
    nothing, and nothing on this path commands them, but the arm is one frame from moving.

    Args:
        clock: The monotonic source the session's boards, lease and latch all read.

    Returns:
        (ArmBackend) The session over both arms, and the teardown that closes them.

    Raises:
        ArmChannelsUnavailableError: If either side has no present, identified channel, or if
            another process holds one of the channel locks.
    """
    interfaces = resolve_arm_channels()
    lock_manager = LockManager()
    acquired = lock_manager.acquire_all([interfaces[side] for side in ARM_SIDES])
    if not acquired.ok:
        raise ArmChannelsUnavailableError(
            f"{acquired.blocked_iface} is locked by {acquired.holder}. One reader per channel "
            "(01 FR-SYS-005): a second one takes replies the first is waiting for, and those "
            "motors read as absent."
        )
    robot = BiOaOpenArmFollower(BiOaOpenArmFollowerConfig(id=REAL_ROBOT_ID), ports=interfaces)
    try:
        robot.connect_readonly(lock_manager)
    except BaseException:
        lock_manager.release_all()
        raise
    session = ArmSession(
        clock=clock,
        read_arms={
            Side.LEFT.value: RealSideReader(robot.left_arm),
            Side.RIGHT.value: RealSideReader(robot.right_arm),
        },
    )
    return ArmBackend(session=session, close=RealBackendTeardown(robot, lock_manager))


def build_arm_backend(backend: str, clock: Clock) -> ArmBackend:
    """Build the arm backend for a named choice; `ARM_BACKEND_NONE` builds no session.

    Args:
        backend: One of `ARM_BACKENDS`.
        clock: The monotonic source the session's boards, lease and latch all read.

    Returns:
        (ArmBackend) The session and its teardown; the session is None for `ARM_BACKEND_NONE`.

    Raises:
        ValueError: If the name is not one of `ARM_BACKENDS`. Refused rather than treated as
            "no arm", because a typo would then be indistinguishable from the default and the
            operator would be told the server came up exactly as they asked.
        ArmChannelsUnavailableError: For `ARM_BACKEND_REAL`, when the channels cannot be
            resolved or locked.
    """
    if backend == ARM_BACKEND_NONE:
        return ArmBackend(session=None, close=NoBackendTeardown())
    if backend == ARM_BACKEND_REAL:
        return _build_real_backend(clock)
    if backend != ARM_BACKEND_DUMMY:
        raise ValueError(f"unknown arm backend {backend!r}; one of {', '.join(ARM_BACKENDS)}")
    robot = DummyOpenArmRobot(DummyRobotConfig(id=DUMMY_ROBOT_ID))
    robot.connect()
    session = ArmSession(
        clock=clock,
        read_arms={side: DummySideReader(robot, side) for side in ARM_SIDES},
    )
    return ArmBackend(session=session, close=DummyBackendTeardown(robot))


__all__ = [
    "ARM_BACKENDS",
    "ARM_BACKENDS_ON_HARDWARE",
    "ARM_BACKEND_DUMMY",
    "ARM_BACKEND_NONE",
    "ARM_BACKEND_REAL",
    "ArmBackend",
    "ArmChannelsUnavailableError",
    "DummyBackendTeardown",
    "DummySideReader",
    "NoBackendTeardown",
    "RealBackendTeardown",
    "RealSideReader",
    "build_arm_backend",
    "resolve_arm_channels",
]
