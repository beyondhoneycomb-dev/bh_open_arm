"""The dummy bimanual OpenArm follower — the real Robot ABC, no CAN (FR-SIM-098).

`DummyOpenArmRobot` is a drop-in for a real backend: it subclasses the frozen
`OpenArmRobot` and therefore inherits — never redeclares — the 48-channel
observation contract and the 16-channel position action contract. A caller that
holds an `OpenArmRobot` cannot tell it apart from a real follower at the interface,
which is what makes the dummy↔real swap a zero-line change for that caller
(acceptance ②).

What the dummy deliberately does NOT do is touch CAN. There is no socket, no
`python-can`, no `AF_CAN` anywhere in its construction, connection, observation, or
action path (acceptance ③, FR-SIM-098: SIM mode never opens the bus). Its state is
a synthetic joint frame advanced in memory. That is the whole point: the entire
teleop/record/inference loop can be exercised with no hardware and no bus.

Fault injection rides on `self.fault` (a `FaultInjection`), default healthy. It is a
runtime affordance, not a config field, so an injected fault never changes how the
device is constructed — the swap contract is preserved even for a faulty dummy.
"""

from __future__ import annotations

from lerobot.robots.robot import RobotAction, RobotObservation

# DROP_COUNTER_META is sourced from the frozen contract so the dummy surfaces the
# CAN drop counter under the same name the real follower does (01 FR-SYS-018).
from contracts.action import DROP_COUNTER_META
from contracts.plugin.robot_abc import OpenArmRobot, openarm_observation_features
from packages.lerobot_robot_openarm_dummy.config import DUMMY_ROBOT_TYPE, DummyRobotConfig
from packages.lerobot_robot_openarm_dummy.injection import FaultInjection

# A small deterministic per-step position increment (degrees) so consecutive
# healthy frames differ, which is what makes a reused (dropped) frame observable.
_POSITION_STEP_DEG = 0.01


class PartialConnectionError(RuntimeError):
    """Raised when a bimanual follower comes up with only some arm channels attached.

    A half-connected bimanual follower must not operate: running one arm while the
    other is dead is the failure the partial-connect scenario provokes, and refusing
    the connection is the mandated upstream reaction.
    """


class DummyOpenArmRobot(OpenArmRobot):
    """A CAN-free bimanual follower that returns the real observation schema.

    Ownership: owns only its synthetic in-memory state and a `FaultInjection`. It
    holds no CAN handle, no socket, and no producer — it is a leaf device a loop
    drives, not a source of authority over the bus.
    """

    name = DUMMY_ROBOT_TYPE
    config_class = DummyRobotConfig

    def __init__(self, config: DummyRobotConfig) -> None:
        """Construct the dummy follower without opening any bus.

        Args:
            config: The dummy follower config. `calibration_dir` may point anywhere
                writable; the dummy never calibrates against hardware.
        """
        super().__init__(config)
        self._connected = False
        self._step = 0
        self._drop_count = 0
        self._last_frame: dict[str, float | int] | None = None
        self._last_observation_latency_sec = 0.0
        self.fault = FaultInjection.none()

    @property
    def is_connected(self) -> bool:
        """Whether the dummy follower is connected (no bus is ever opened)."""
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        """A dummy is always calibrated: it has no hardware offsets to find."""
        return True

    @property
    def last_observation_latency_sec(self) -> float:
        """Simulated seconds the most recent `get_observation` took.

        Returns:
            (float) The injected response lag of the last observation, or 0 when the
            device answered promptly. The upstream deadline monitor reads this.
        """
        return self._last_observation_latency_sec

    def connect(self, calibrate: bool = True) -> None:
        """Come online without touching CAN; refuse a half-connected bimanual pair.

        Args:
            calibrate: Whether to calibrate after connecting (a no-op for a dummy).

        Raises:
            PartialConnectionError: If the injected fault names arm channels that
                fail to attach — the bimanual pair must not run half-connected.
        """
        if self.fault.fail_channels:
            raise PartialConnectionError(
                f"bimanual follower channels {self.fault.fail_channels} did not attach; "
                "refusing to operate a half-connected pair"
            )
        self._connected = True
        if calibrate and not self.is_calibrated:
            self.calibrate()

    def calibrate(self) -> None:
        """No-op: a dummy has no motor offsets to collect."""

    def configure(self) -> None:
        """No-op: a dummy has no motor parameters to apply."""

    def get_observation(self) -> RobotObservation:
        """Return a synthetic frame in the real schema, honouring the armed fault.

        Healthy: a fresh in-memory joint frame, field-identical to the real schema.
        Obs-missing: the named channels are omitted (a sensor that failed to report).
        Packet-drop: the previous frame is reused and the CAN drop counter is
        incremented (01 FR-SYS-018), never a new reading.

        Returns:
            (RobotObservation) The observation frame; a flat dict of channel name to
            scalar, matching `observation_features`.

        Raises:
            RuntimeError: If called while not connected (LeRobot Robot contract).
        """
        if not self._connected:
            raise RuntimeError("get_observation called on a disconnected dummy follower")

        self._last_observation_latency_sec = self.fault.response_lag_sec

        if self.fault.packet_drop and self._last_frame is not None:
            self._drop_count += 1
            frame = dict(self._last_frame)
            frame[DROP_COUNTER_META] = self._drop_count
            self._last_frame = frame
            return dict(frame)

        frame = self._build_frame()
        self._last_frame = dict(frame)
        self._step += 1

        for channel in self.fault.drop_channels:
            frame.pop(channel, None)
        return frame

    def send_action(self, action: RobotAction) -> RobotAction:
        """Accept a position action and echo what was 'sent'; no CAN is written.

        Args:
            action: A position action matching `action_features`.

        Returns:
            (RobotAction) The action as applied. A dummy applies it verbatim — there
            is no bus to clip against — so the returned action equals the input.

        Raises:
            RuntimeError: If called while not connected (LeRobot Robot contract).
        """
        if not self._connected:
            raise RuntimeError("send_action called on a disconnected dummy follower")
        return dict(action)

    def disconnect(self) -> None:
        """Go offline. Nothing to release: no bus was ever opened."""
        self._connected = False

    def _build_frame(self) -> dict[str, float | int]:
        """Build one full synthetic observation frame in the real schema.

        Returns:
            (dict[str, float | int]) Every one of the 48 channels as a float plus the
            CAN drop counter as an int, keyed exactly as `observation_features`.
        """
        frame: dict[str, float | int] = {}
        for channel in openarm_observation_features(bimanual=True):
            if channel == DROP_COUNTER_META:
                continue
            frame[channel] = self._channel_value(channel)
        frame[DROP_COUNTER_META] = self._drop_count
        return frame

    def _channel_value(self, channel: str) -> float:
        """Return a deterministic scalar for a channel, advancing with the step.

        Position (`.pos`) channels drift by a fixed increment each frame so a reused
        frame is distinguishable from a fresh one; velocity and torque report zero
        (a still, unloaded synthetic arm).

        Args:
            channel: The channel name.

        Returns:
            (float) The synthetic scalar for this channel this step.
        """
        if channel.endswith(".pos"):
            return float(self._step * _POSITION_STEP_DEG)
        return 0.0
