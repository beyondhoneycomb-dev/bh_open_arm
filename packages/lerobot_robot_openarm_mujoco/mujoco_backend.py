"""BiOpenArmMujoco: the stage-1 canonical MuJoCo backend on the OpenArm Robot ABC.

`09` FR-SIM-097 puts MuJoCo, Isaac, and the hardware follower on ONE LeRobot Robot
ABC; this is the MuJoCo implementation (`09`, stage-1 canonical/default). It drives
the WP-0C-03-corrected MJCF through position actuators:

- `send_action` converts the LeRobot degree action to radians at the single
  `sim.mujoco.sim_sync` boundary and writes actuator ctrl (`09` send_action).
- `get_observation` returns the frozen CTR-ACT observation in degrees (the LeRobot
  boundary is degrees), reusing the same boundary module for the reverse crossing.

No CAN socket is ever opened and no flock acquired (`09` FR-SIM-098, `01` §4.1):
the `can_guard` runtime hook is re-checked at connect and before every actuation,
and this module contains no CAN-open primitive (proven by tests/wp0c01).

Importing this module imports the robot stack (LeRobot) and `mujoco`; it is product
code. The pure backend selection and CAN guard live in sibling modules that import
neither, so they stay usable in the light lane.
"""

from __future__ import annotations

from lerobot.robots.robot import Robot
from lerobot.types import RobotAction, RobotObservation
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from contracts.action.observation import DROP_COUNTER_META
from contracts.plugin.robot_abc import OpenArmRobot
from packages.lerobot_robot_openarm_mujoco.can_guard import assert_no_can_open
from packages.lerobot_robot_openarm_mujoco.config_mujoco import BiOpenArmMujocoConfig
from sim.mujoco.scene import MujocoScene
from sim.mujoco.sim_sync import POSITION_SUFFIX, lerobot_to_mjcf, mjcf_to_lerobot

# A SIM backend never drops a CAN packet, so the drop-counter meta (01 FR-SYS-018)
# is always zero -- but it is always present, because the frozen observation schema
# names it as a channel.
_NO_DROPPED_PACKETS = 0

# The channel-name suffix marking a position action entry (`left_joint_1.pos`).
_POSITION_CHANNEL_SUFFIX = f".{POSITION_SUFFIX}"


class BiOpenArmMujoco(OpenArmRobot):
    """The MuJoCo bimanual backend, a drop-in on the shared Robot ABC (FR-SIM-097).

    Ownership/lifecycle: holds one `MujocoScene` while connected and releases it on
    disconnect. `get_observation` and `send_action` require a connected scene and
    raise otherwise, per the LeRobot Robot contract. Single control loop -- not
    thread-safe. SIM mode: opens zero CAN sockets for the object's whole life.
    """

    config_class = BiOpenArmMujocoConfig
    name = "bi_openarm_mujoco"

    def __init__(self, config: BiOpenArmMujocoConfig) -> None:
        """Bind the config; the scene is loaded lazily on `connect`.

        Args:
            config: The MuJoCo backend config.
        """
        super().__init__(config)
        self._config = config
        self._scene: MujocoScene | None = None
        self._connected = False
        # SIM opens no CAN socket; this counter stays zero for the object's life and
        # is what the can_guard runtime hook checks (09 FR-SIM-098, acceptance ②).
        self._can_open_count = 0

    @property
    def is_connected(self) -> bool:
        """Whether the backend holds a loaded scene."""
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        """Always True: a simulated model has no motor offsets to calibrate."""
        return True

    def connect(self, calibrate: bool = True) -> None:
        """Load the MJCF scene. Opens no CAN socket and acquires no flock.

        Args:
            calibrate: Accepted for the Robot ABC; simulation has nothing to
                calibrate, so it is a no-op here.

        Raises:
            DeviceAlreadyConnectedError: If already connected.
        """
        if self._connected:
            raise DeviceAlreadyConnectedError(f"{self} is already connected")
        # Runtime hook: entering the connect path in SIM must find zero CAN opens.
        assert_no_can_open(self._can_open_count)
        self._scene = MujocoScene.load(self._config.mjcf_path)
        self._connected = True
        if calibrate and not self.is_calibrated:
            self.calibrate()
        self.configure()

    def disconnect(self) -> None:
        """Release the scene.

        Raises:
            DeviceNotConnectedError: If not connected.
        """
        if not self._connected:
            raise DeviceNotConnectedError(f"{self} is not connected")
        self._scene = None
        self._connected = False

    def calibrate(self) -> None:
        """No-op: a simulated model needs no motor-offset calibration (Robot ABC)."""
        return

    def configure(self) -> None:
        """Reset the scene to its home configuration.

        Raises:
            DeviceNotConnectedError: If not connected.
        """
        self._require_scene().reset()

    def get_observation(self) -> RobotObservation:
        """Return the frozen 48-channel observation in degrees, plus the drop meta.

        Returns:
            (RobotObservation) One entry per `observation_features` channel: joint
            positions in degrees, velocities in degrees/second, torques in
            newton-metres, and the CAN drop counter (always zero in SIM).

        Raises:
            DeviceNotConnectedError: If not connected.
        """
        joint_state = self._require_scene().read_joint_state()
        observation: RobotObservation = dict(mjcf_to_lerobot(joint_state))
        observation[DROP_COUNTER_META] = _NO_DROPPED_PACKETS
        return observation

    def send_action(self, action: RobotAction) -> RobotAction:
        """Write the position action to MJCF ctrl; opens no CAN socket.

        The degree action crosses to radians at the single `sim.mujoco.sim_sync`
        boundary, then is written to the position actuators. The accepted position
        action (degrees) is echoed back, matching `action_features`.

        Args:
            action: Position action, `<motor>.pos` channels in degrees.

        Returns:
            (RobotAction) The accepted position action, in degrees.

        Raises:
            DeviceNotConnectedError: If not connected.
        """
        scene = self._require_scene()
        # Runtime hook: actuating in SIM must never route through a CAN open.
        assert_no_can_open(self._can_open_count)
        goal_deg = {
            name: float(value)
            for name, value in action.items()
            if name.endswith(_POSITION_CHANNEL_SUFFIX)
        }
        scene.write_ctrl(lerobot_to_mjcf(goal_deg))
        return goal_deg

    def _require_scene(self) -> MujocoScene:
        """Return the connected scene, or raise if the backend is not connected."""
        if not self._connected or self._scene is None:
            raise DeviceNotConnectedError(f"{self} is not connected; call connect() first")
        return self._scene


# The backend must resolve every abstract method of the LeRobot Robot ABC -- a
# stray unimplemented signature would leave the class abstract and uninstantiable
# (acceptance ①). This asserts it at import time so a regression is caught here,
# not deep in a training loop.
assert not getattr(BiOpenArmMujoco, "__abstractmethods__", frozenset()), (
    f"BiOpenArmMujoco leaves abstract methods unimplemented: "
    f"{sorted(BiOpenArmMujoco.__abstractmethods__)}"
)
assert issubclass(BiOpenArmMujoco, Robot)
