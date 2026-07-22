"""The VR teleoperator is a LeRobot plugin (LeRobot diff = 0), identity from `CTR-TEL@v1`.

The plugin identity — distribution prefix, `--teleop.type`, config/device class — is
consumed from the frozen contract, never restated here. The UDP source that backs it
is a `PoseSource` whose `frame_applied` is already declared, so WP-3B-09/10 consume
one interface regardless of the transport.
"""

from __future__ import annotations

from backend.teleop.vr_udp import (
    UDP_PORT_DEFAULT,
    PoseSource,
    VrUdpPoseSource,
    make_vr_pose_source,
    vr_plugin_identity,
)
from contracts.teleop import (
    TELEOPERATOR_DIST_PREFIX,
    VR_CONFIG_CLASS,
    VR_DEVICE_CLASS,
    VR_DIST_NAME,
    VR_TELEOP_TYPE,
)


def test_identity_matches_frozen_contract() -> None:
    """The identity is exactly the frozen `CTR-TEL@v1` names, verified for discovery."""
    identity = vr_plugin_identity()
    assert identity.dist_name == VR_DIST_NAME
    assert identity.dist_name.startswith(TELEOPERATOR_DIST_PREFIX)
    assert identity.teleop_type == VR_TELEOP_TYPE
    assert identity.config_class == VR_CONFIG_CLASS
    assert identity.device_class == VR_DEVICE_CLASS


def test_device_class_derives_from_config_class() -> None:
    """The device class is the config class name with `Config` stripped (LeRobot rule)."""
    identity = vr_plugin_identity()
    assert identity.config_class.endswith("Config")
    assert identity.device_class == identity.config_class[: -len("Config")]


def test_make_source_is_a_pose_source() -> None:
    """The plugin's source is a started-elsewhere `PoseSource` with the frame applied."""
    source = make_vr_pose_source()
    assert isinstance(source, VrUdpPoseSource)
    assert isinstance(source, PoseSource)
    assert source.frame_applied is True


def test_default_port_is_the_contract_port() -> None:
    """The frozen UDP port is `:5006` (`FR-TEL-014`)."""
    assert UDP_PORT_DEFAULT == 5006


def test_make_source_honours_a_port_override() -> None:
    """The override path binds the requested address (here loopback, ephemeral)."""
    source = make_vr_pose_source(host="127.0.0.1", port=0)
    source.start()
    try:
        assert source.bound_port is not None
        assert source.bound_port != 0  # an ephemeral port was assigned
    finally:
        source.stop()
