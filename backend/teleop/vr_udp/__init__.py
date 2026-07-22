"""VR teleoperator UDP pose source (WP-3B-07).

The Quest APK path A of the VR teleoperator: a `:5006` newline-terminated UTF-8
JSON receiver (`quest_receiver` semantics), the coordinate-transform chain into the
robot-world EE frame, the three-level per-arm validity model, and preservation of
both the source `t` and the PC receive instant. It is the source half of the
LeRobot VR teleoperator plugin (LeRobot diff = 0); the clutch/smoother/IK/safety
body is WP-3B-09/10, which consume `PoseSource` from here.

Everything runs on the frozen synthetic stream (`contracts/fixtures`); a real Meta
Quest is deferred to `deferred.py`'s SKIP-with-reason and re-verification hook
(`02a` §4.1, the ONE RULE). This package consumes `CTR-TEL@v1` by import and
restates none of it.
"""

from __future__ import annotations

from backend.teleop.vr_udp.constants import (
    FRAME_APPLIED,
    FRAME_OFFSET,
    Q_ROBOT,
    R_ROBOT,
    UDP_PORT_DEFAULT,
)
from backend.teleop.vr_udp.deferred import (
    REAL_FIXTURE_ENV_VAR,
    capture_path_from_env,
    real_vr_supported,
    replay_from_capture,
)
from backend.teleop.vr_udp.frame import ArmPose, VrFrame
from backend.teleop.vr_udp.plugin import (
    VrPluginIdentity,
    make_vr_pose_source,
    vr_plugin_identity,
)
from backend.teleop.vr_udp.protocol import FrameParseError, parse_datagram, split_frames
from backend.teleop.vr_udp.source import PoseSource, VrUdpPoseSource
from backend.teleop.vr_udp.transform import WorldPose, transform_controller_pose

__all__ = [
    "FRAME_APPLIED",
    "FRAME_OFFSET",
    "REAL_FIXTURE_ENV_VAR",
    "Q_ROBOT",
    "R_ROBOT",
    "UDP_PORT_DEFAULT",
    "ArmPose",
    "FrameParseError",
    "PoseSource",
    "VrFrame",
    "VrPluginIdentity",
    "VrUdpPoseSource",
    "WorldPose",
    "capture_path_from_env",
    "make_vr_pose_source",
    "parse_datagram",
    "real_vr_supported",
    "replay_from_capture",
    "split_frames",
    "transform_controller_pose",
    "vr_plugin_identity",
]
