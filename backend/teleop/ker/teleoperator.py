"""The KER teleoperator — a LeRobot plugin that streams joint angles, no IK (WP-3B-14).

`OpenArmKER` wraps the KER USB encoder as a LeRobot `Teleoperator`, exactly the plugin
surface the VR teleoperator and the dummy leader implement (05 §2.3, FR-TEL-062). Its
one difference from the VR path is the IK stage, which it omits: the KER reads joint
angles, so `get_action()` returns them directly as `.pos` degrees with `.vel`/`.torque`
honest zeros (FR-TEL-064). It opens no CAN channel, so inserting it changes no CAN DAG
(FR-TEL-063).

The clutch, tracking state machine and safety gate are NOT re-implemented here: they
are the source-agnostic pipeline (WP-3B-09/10) that wraps a VR or KER source
identically (05 §2.7). This plugin is only the source — it exposes the same three-level
`tracking_validity` that pipeline consumes and adds no parallel safety path, which is
what "same code path as VR" means (acceptance ③). Bilateral force feedback is
impossible on the KER (motorless), so `feedback_features` is empty (FR-TEL-065).
"""

from __future__ import annotations

from typing import Any

from lerobot.teleoperators.teleoperator import Teleoperator

from backend.teleop.ker.config import OpenArmKERConfig
from backend.teleop.ker.device import KerDevice, UsbKerDevice
from backend.teleop.ker.keyset import ker_action, ker_action_features
from contracts.teleop import (
    FEEDBACK_FEATURES,
    KER_TELEOP_TYPE,
    KerInsertionSlot,
    TeleopValidity,
    reserved_ker_slot,
)


class OpenArmKER(Teleoperator):
    """The KER leader: a joint-angle source behind the LeRobot Teleoperator ABC.

    Ownership: owns its connection flag, the injected `KerDevice`, and the last
    tracking validity it read. It holds no clutch, smoother, heartbeat, or workspace
    state — those live in the shared teleop pipeline. The device defaults to the real
    `UsbKerDevice`, which fails loudly without hardware; a test injects a mock before
    connect() rather than the plugin ever defaulting to synthetic data.
    """

    name = KER_TELEOP_TYPE
    config_class = OpenArmKERConfig

    def __init__(self, config: OpenArmKERConfig) -> None:
        """Construct the KER leader without opening the USB device.

        Args:
            config: The KER leader config.
        """
        super().__init__(config)
        self.config = config
        self._connected = False
        self._last_validity = TeleopValidity.OK
        self.device: KerDevice = UsbKerDevice(config.usb_vid, config.usb_pid)

    @property
    def action_features(self) -> dict[str, type]:
        """The KER action keyset: position channels, with honest-zero vel/torque on."""
        return ker_action_features(self.config.bimanual, self.config.use_velocity_and_torque)

    @property
    def feedback_features(self) -> dict[str, type]:
        """No feedback channels: the KER is motorless, so force feedback cannot exist."""
        return dict(FEEDBACK_FEATURES)

    @property
    def is_connected(self) -> bool:
        """Whether the KER device is connected."""
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        """Always calibrated: the KER's magnetic encoders read absolute joint angles."""
        return True

    @property
    def tracking_validity(self) -> TeleopValidity:
        """The tracking validity of the last frame — the shared state machine's input.

        This is the same three-level model a VR source exposes (CTR-TEL@v1); the
        pipeline's heartbeat/state machine consumes it identically for either source.
        """
        return self._last_validity

    def insertion_slot(self) -> KerInsertionSlot:
        """Return the contract's reserved KER slot: USB, zero CAN channels, no IK."""
        return reserved_ker_slot()

    def connect(self, calibrate: bool = True) -> None:
        """Open the KER device.

        Args:
            calibrate: Whether to calibrate after connecting (a no-op for the KER).
        """
        self.device.connect()
        self._connected = True
        if calibrate and not self.is_calibrated:
            self.calibrate()

    def calibrate(self) -> None:
        """No-op: the KER's magnetic encoders are absolute, so there is no zero to set."""

    def configure(self) -> None:
        """No-op: the KER has no runtime parameters to apply."""

    def sync_state(self, obs: dict[str, Any]) -> None:
        """Accept the loop observation the operational path passes before get_action().

        The VR teleoperator uses this to push measured angles into its IK
        configuration (FR-TEL-006). The KER performs no IK, so there is nothing to
        sync; the method exists — non-abstract — so the operational loop's call site is
        identical for a VR or a KER source (05 §2.6).

        Args:
            obs: The robot observation; unused because the KER runs no IK.
        """
        del obs

    def get_action(self) -> dict[str, float]:
        """Return the latest joint angles as a position action — no IK (FR-TEL-064).

        Reads one KER frame and maps its joint angles directly onto the `.pos`
        channels in degrees; every `.vel`/`.torque` channel is the honest zero. No
        inverse kinematics, coordinate transform, or IK integration touches the value,
        so the action is a deterministic identity of the joints the leader reads.

        Returns:
            (dict[str, float]) One float per `action_features` key.

        Raises:
            RuntimeError: If called while not connected (LeRobot Teleoperator contract).
        """
        if not self._connected:
            raise RuntimeError("get_action called on a disconnected KER leader")
        reading = self.device.read()
        self._last_validity = reading.validity
        return ker_action(
            reading.joint_angles_deg,
            self.config.bimanual,
            self.config.use_velocity_and_torque,
        )

    def send_feedback(self, feedback: dict[str, float]) -> None:
        """Accept and discard feedback: the motorless KER has no force channel to drive.

        Args:
            feedback: Feedback channels a follower would return; ignored (the OpenArm
                path never calls this, 05 §2.13).
        """
        del feedback

    def disconnect(self) -> None:
        """Release the KER device."""
        self.device.disconnect()
        self._connected = False
