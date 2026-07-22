"""The OpenArm hardware follower plugin (`lerobot_robot_openarm`, 01 FR-SYS-014).

A `lerobot_robot_*` third-party plugin distribution: importing it registers the
OpenArm follower `RobotConfig` choices (`config_oa`) and a resolution probe
(`registration`) through `@RobotConfig.register_subclass`, so LeRobot picks the
backend up via `register_third_party_plugins()` + the `make_robot_from_config`
fallback — with zero edits to LeRobot proper (01 FR-SYS-003).

The hardware follower device class `OaOpenArmFollower` is added to this package by
WP-1-02 (`openarm_follower_oa.py`) under the sequential ownership handover declared
in `06` §3.2; this skeleton owns the registration surface it plugs into. Importing
`OpenArmPluginProbe` here (from `registration`) also makes it resolvable from this
package's namespace, which is where `make_device_from_device_class` looks for a
device class named after its config.
"""

from __future__ import annotations

from packages.lerobot_robot_openarm.config_oa import (
    BI_OA_FOLLOWER_TYPE,
    OA_FOLLOWER_TYPE,
    BiOaOpenArmFollowerConfig,
    OaOpenArmFollowerConfig,
)
from packages.lerobot_robot_openarm.registration import (
    PLUGIN_MODULE_NAME,
    PROBE_TYPE,
    OpenArmPluginProbe,
    OpenArmPluginProbeConfig,
    discover_plugins,
)

__all__ = [
    "BI_OA_FOLLOWER_TYPE",
    "OA_FOLLOWER_TYPE",
    "PLUGIN_MODULE_NAME",
    "PROBE_TYPE",
    "BiOaOpenArmFollowerConfig",
    "OaOpenArmFollowerConfig",
    "OpenArmPluginProbe",
    "OpenArmPluginProbeConfig",
    "discover_plugins",
]
