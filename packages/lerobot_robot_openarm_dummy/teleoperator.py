"""The dummy leader — a CAN-free source of position actions (FR-SYS-003).

`DummyOpenArmTeleoperator` stands in for a real leader (VR or KER): it produces the
16-channel position action a follower consumes, using the frozen action contract so
its `action_features` match the follower's exactly. Like the dummy follower it
opens no bus and spawns no process — it is a pure in-memory source a loop polls.

Its one fault lever is `stall`: a leader that stops producing fresh actions. A
stalled leader does not error; it simply goes quiet, and the mandated upstream
reaction is the scheduler ageing the last target into a stale-source hold rather
than continuing to command on a dead source. `is_producing()` is what a driving
loop consults to decide whether a fresh action exists to publish.
"""

from __future__ import annotations

from lerobot.teleoperators.teleoperator import Teleoperator

from contracts.plugin.robot_abc import openarm_action_features
from packages.lerobot_robot_openarm_dummy.config import DUMMY_TELEOP_TYPE, DummyTeleoperatorConfig
from packages.lerobot_robot_openarm_dummy.injection import FaultInjection

# A fixed neutral commanded position (degrees) for every action channel. Zero is not
# a claim about the arm; it is a well-formed, deterministic stand-in target.
_NEUTRAL_ACTION_DEG = 0.0


class DummyOpenArmTeleoperator(Teleoperator):
    """A CAN-free leader producing the frozen 16-channel position action.

    Ownership: owns only its connection flag and a `FaultInjection`. It holds no
    mailbox, scheduler, or bus handle — a loop reads `get_action()` and decides what
    to do with the result.
    """

    name = DUMMY_TELEOP_TYPE
    config_class = DummyTeleoperatorConfig

    def __init__(self, config: DummyTeleoperatorConfig) -> None:
        """Construct the dummy leader without opening any bus.

        Args:
            config: The dummy leader config.
        """
        super().__init__(config)
        self._connected = False
        self.fault = FaultInjection.none()

    @property
    def action_features(self) -> dict[str, type]:
        """The frozen 16-channel position action contract (shared with the follower)."""
        return openarm_action_features(bimanual=True)

    @property
    def feedback_features(self) -> dict[str, type]:
        """No feedback channels: the dummy leader consumes no follower feedback."""
        return {}

    @property
    def is_connected(self) -> bool:
        """Whether the dummy leader is connected (no bus is ever opened)."""
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        """A dummy leader is always calibrated: it has no offsets to find."""
        return True

    def connect(self, calibrate: bool = True) -> None:
        """Come online without touching CAN.

        Args:
            calibrate: Whether to calibrate after connecting (a no-op for a dummy).
        """
        self._connected = True
        if calibrate and not self.is_calibrated:
            self.calibrate()

    def calibrate(self) -> None:
        """No-op: a dummy leader has no offsets to collect."""

    def configure(self) -> None:
        """No-op: a dummy leader has no parameters to apply."""

    def is_producing(self) -> bool:
        """Whether the leader is currently producing fresh actions.

        Returns:
            (bool) False when the `stall` fault is armed — a source gone quiet.
        """
        return not self.fault.stall

    def get_action(self) -> dict[str, float]:
        """Return the current neutral position action in the frozen action schema.

        Returns:
            (dict[str, float]) One float per action channel, keyed exactly as
            `action_features`.

        Raises:
            RuntimeError: If called while not connected (LeRobot Teleoperator
                contract).
        """
        if not self._connected:
            raise RuntimeError("get_action called on a disconnected dummy leader")
        return dict.fromkeys(self.action_features, _NEUTRAL_ACTION_DEG)

    def send_feedback(self, feedback: dict[str, float]) -> None:
        """Accept and discard follower feedback: the dummy leader has no actuators.

        Args:
            feedback: Feedback channels the follower would return; ignored.
        """
        del feedback

    def disconnect(self) -> None:
        """Go offline. Nothing to release: no bus was ever opened."""
        self._connected = False
