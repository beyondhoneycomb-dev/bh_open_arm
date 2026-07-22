"""The plugin registration path and its live resolution proof (01 FR-SYS-014).

`register_third_party_plugins()` (lerobot `utils/import_utils.py`) discovers
installed distributions whose name starts with `lerobot_robot_` /
`lerobot_teleoperator_` / `lerobot_camera_` (and `_policy_` / `_env_`) and imports
them; importing this package runs the `@RobotConfig.register_subclass` side effects
in `config_oa`, which is the entire registration mechanism — no LeRobot source is
edited (01 FR-SYS-003).

`OpenArmPluginProbe` is a minimal concrete backend whose only job is to prove, before
the hardware follower lands (WP-1-02 owns `openarm_follower_oa.py` under the
sequential handover), that `make_robot_from_config` resolves THIS plugin package
through its third-party fallback (robots/utils.py else-branch ->
`make_device_from_device_class`). It inherits the frozen `OpenArmRobot` schema and
implements the ABC minimally; it opens no bus and holds no hardware. It is not the
follower — it is the plugin declaring "my registration wiring is live."
"""

from __future__ import annotations

from dataclasses import dataclass

from lerobot.robots.config import RobotConfig
from lerobot.robots.robot import RobotAction, RobotObservation
from lerobot.utils.import_utils import register_third_party_plugins

from contracts.plugin.robot_abc import OpenArmRobot, openarm_observation_features

# The importable module name of this plugin, and the distribution name a deploy
# build publishes. It matches the `lerobot_robot_` prefix
# `register_third_party_plugins` scans for (acceptance (1)/(2)).
PLUGIN_MODULE_NAME = "lerobot_robot_openarm"

# The registration probe's choice name. Distinct from the follower types and from
# LeRobot's hardcoded branch names, so it too resolves through the fallback.
PROBE_TYPE = "oa_plugin_probe"


def discover_plugins() -> None:
    """Run LeRobot's third-party plugin discovery.

    Thin pass-through to `register_third_party_plugins()` so callers exercise the
    real discovery entry point rather than a reimplementation of it.
    """
    register_third_party_plugins()


@RobotConfig.register_subclass(PROBE_TYPE)
@dataclass(kw_only=True)
class OpenArmPluginProbeConfig(RobotConfig):
    """Config whose sole purpose is to prove the third-party fallback resolves this package."""


class OpenArmPluginProbe(OpenArmRobot):
    """A minimal concrete OpenArm backend proving `make_robot_from_config` resolves us.

    Ownership: holds only an in-memory connected flag. It opens no CAN socket, spawns
    no process, and is not a hardware follower — the real follower is WP-1-02's
    `OaOpenArmFollower`. This class exists so the registration/resolution path is
    verifiable at WP-1-01 time, before that follower exists.
    """

    config_class = OpenArmPluginProbeConfig
    name = PROBE_TYPE

    def __init__(self, config: OpenArmPluginProbeConfig) -> None:
        """Construct the probe without opening any bus."""
        super().__init__(config)
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Whether the probe is connected (no bus is ever opened)."""
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        """A probe is always calibrated: it has no hardware offsets to find."""
        return True

    def connect(self, calibrate: bool = True) -> None:
        """Come online without touching any bus."""
        self._connected = True
        if calibrate and not self.is_calibrated:
            self.calibrate()

    def calibrate(self) -> None:
        """No-op: the probe has no motor offsets to collect."""

    def configure(self) -> None:
        """No-op: the probe has no motor parameters to apply."""

    def get_observation(self) -> RobotObservation:
        """Return a schema-valid zero frame in the frozen bimanual observation shape."""
        features = openarm_observation_features(bimanual=True)
        return {name: (0 if declared is int else 0.0) for name, declared in features.items()}

    def send_action(self, action: RobotAction) -> RobotAction:
        """Echo the requested action unchanged (the probe applies nothing)."""
        return dict(action)

    def disconnect(self) -> None:
        """Go offline; nothing to release."""
        self._connected = False
