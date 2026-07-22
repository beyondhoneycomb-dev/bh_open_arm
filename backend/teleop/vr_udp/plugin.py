"""The VR teleoperator's LeRobot-plugin identity, consumed from `CTR-TEL@v1`.

The teleoperator is an unmodified LeRobot plugin (LeRobot diff = 0): it is
discovered by the `lerobot_teleoperator_openarm_` distribution prefix and selected
by `--teleop.type openarm_vr`. Those names are frozen in `CTR-TEL@v1` and consumed
here by import, never restated (`02b` §5.0b) — this module binds the UDP source to
that identity and re-checks the discovery convention, so a rename of the frozen
contract surfaces here rather than silently diverging.

The full `Teleoperator` device class (its IK-bearing `get_action`) is assembled
downstream by WP-3B-09, which consumes this source; this module carries only the
plugin identity and the pose-source binding.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.teleop.vr_udp.source import VrUdpPoseSource
from contracts.teleop import (
    VR_CONFIG_CLASS,
    VR_DEVICE_CLASS,
    VR_DIST_NAME,
    VR_TELEOP_TYPE,
    device_class_from_config_class,
    require_plugin_convention,
)


@dataclass(frozen=True)
class VrPluginIdentity:
    """The frozen `CTR-TEL@v1` identity of the VR teleoperator plugin.

    Attributes:
        dist_name: The pip distribution LeRobot auto-imports by prefix.
        teleop_type: The `--teleop.type` selector.
        config_class: The `@register_subclass` config class name.
        device_class: The device class name LeRobot resolves from the config name.
    """

    dist_name: str
    teleop_type: str
    config_class: str
    device_class: str


def vr_plugin_identity() -> VrPluginIdentity:
    """Return the VR teleoperator plugin identity, verified against the convention.

    Returns:
        (VrPluginIdentity) The frozen identity from `CTR-TEL@v1`.

    Raises:
        PluginConventionError: If the frozen names ever break LeRobot discovery.
    """
    require_plugin_convention(VR_DIST_NAME)
    device_class = device_class_from_config_class(VR_CONFIG_CLASS)
    if device_class != VR_DEVICE_CLASS:
        raise ValueError(
            f"frozen device class {VR_DEVICE_CLASS!r} disagrees with the name resolved "
            f"from {VR_CONFIG_CLASS!r} ({device_class!r})"
        )
    return VrPluginIdentity(
        dist_name=VR_DIST_NAME,
        teleop_type=VR_TELEOP_TYPE,
        config_class=VR_CONFIG_CLASS,
        device_class=device_class,
    )


def make_vr_pose_source(host: str | None = None, port: int | None = None) -> VrUdpPoseSource:
    """Construct the UDP pose source that backs the VR plugin.

    Args:
        host: Optional bind host override.
        port: Optional bind port override.

    Returns:
        (VrUdpPoseSource) A configured, not-yet-started UDP pose source.
    """
    if host is not None and port is not None:
        return VrUdpPoseSource(host=host, port=port)
    if host is not None:
        return VrUdpPoseSource(host=host)
    if port is not None:
        return VrUdpPoseSource(port=port)
    return VrUdpPoseSource()
