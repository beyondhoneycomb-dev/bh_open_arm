"""Which arm the served process holds — the host end of the dummy↔real swap (`FR-SYS-003`).

`01` FR-SYS-003 makes the choice of backend a config token rather than a source edit, and
`backend.actuation.ArmSession` is built to match: it takes one read per arm side and knows
nothing about what is behind them. This module is where a name becomes those reads.

The default is no arm at all, and that is the load-bearing decision here. A server that
defaulted to the dummy would publish synthetic joint angles onto the board an operator reads,
under the same API a real reading arrives through, with nothing on the screen to separate them.
`FR-SIM-098`'s dummy exists so the loop can be exercised with no bus — not so the process has
something to show when it has no arm.

The real backend is deliberately absent from this list. Opening the bus needs the CAN channel
locks (`FR-SYS-005` / `FR-CON-010`), an end-effector record, and a torque-on sequence that is
`WP-1-05`'s and requires a person beside the arm. A name here that quietly did less than that
would be the worst of the three states.

Assembling the process is what this tree does, which is why the import of a `packages/` plugin
lives here rather than in `backend/actuation`: the session takes callables, and choosing what is
behind them is the host's job.
"""

from __future__ import annotations

from backend.actuation.clock import Clock
from backend.actuation.guard import GuardSample
from backend.actuation.session import ArmFrame, ArmSession
from backend.calibration.schema import MOTOR_ORDER
from contracts.prim.schema import ARM_SIDES
from contracts.units import Deg, Nm
from packages.lerobot_robot_openarm_dummy.config import DummyRobotConfig
from packages.lerobot_robot_openarm_dummy.robot import DummyOpenArmRobot

ARM_BACKEND_NONE = "none"
ARM_BACKEND_DUMMY = "dummy"

# The names `oa-serve --arm` accepts, in the order it lists them. The parser reads this rather
# than a second copy, so a name the CLI offers cannot be one `build_arm_session` refuses.
ARM_BACKENDS = (ARM_BACKEND_NONE, ARM_BACKEND_DUMMY)

# The LeRobot instance id the dummy follower is constructed under. It reaches no filesystem and
# no bus; it exists because `RobotConfig` carries the field.
DUMMY_ROBOT_ID = "oa-serve-dummy"

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


def build_arm_session(backend: str, clock: Clock) -> ArmSession | None:
    """Build the arm session for a named backend, or None when this process holds no arm.

    Args:
        backend: One of `ARM_BACKENDS`.
        clock: The monotonic source the session's boards, lease and latch all read.

    Returns:
        (ArmSession | None) The session, or None for `ARM_BACKEND_NONE`.

    Raises:
        ValueError: If the name is not one of `ARM_BACKENDS`. Refused rather than treated as
            "no arm", because a typo would then be indistinguishable from the default and the
            operator would be told the server came up exactly as they asked.
    """
    if backend == ARM_BACKEND_NONE:
        return None
    if backend != ARM_BACKEND_DUMMY:
        raise ValueError(f"unknown arm backend {backend!r}; one of {', '.join(ARM_BACKENDS)}")
    robot = DummyOpenArmRobot(DummyRobotConfig(id=DUMMY_ROBOT_ID))
    robot.connect()
    return ArmSession(
        clock=clock,
        read_arms={side: DummySideReader(robot, side) for side in ARM_SIDES},
    )


__all__ = [
    "ARM_BACKENDS",
    "ARM_BACKEND_DUMMY",
    "ARM_BACKEND_NONE",
    "DummySideReader",
    "build_arm_session",
]
