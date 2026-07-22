"""Shared builders for the WP-3B-09 conditioning tests.

The conditioner consumes the `WP-3B-07` `VrFrame` — a per-arm `ArmPose` (already
world-frame transformed) plus the frozen `CTR-TEL@v1` `TeleopSample`. `make_frame`
builds one with a controllable grip, validity, pose and receive instant for a single
arm, filling the other arm with a neutral pose so the bimanual frame shape is honoured.

`WorldPose` is scalar-FIRST `[px, py, pz, qw, qx, qy, qz]`; the tests express poses in
the scalar-LAST `(x, y, z, w)` order the clutch math uses, so the conversion lives here.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.teleop.vr_udp.frame import ArmPose, VrFrame
from backend.teleop.vr_udp.source import PoseSource
from backend.teleop.vr_udp.transform import WorldPose
from contracts.teleop import TeleopSample, TeleopValidity

IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)
_ZERO_POSITION = (0.0, 0.0, 0.0)
_NEUTRAL_BUTTONS = {"a": False, "b": False, "x": False, "y": False}


def _world_pose(position: Sequence[float], quaternion_xyzw: Sequence[float]) -> WorldPose:
    """Assemble a scalar-first `WorldPose` from a position and a scalar-last quaternion."""
    px, py, pz = position
    qx, qy, qz, qw = quaternion_xyzw
    return (px, py, pz, qw, qx, qy, qz)


def make_frame(
    grip: float,
    validity: TeleopValidity,
    position: Sequence[float],
    quaternion: Sequence[float],
    receive_mono_ns: int,
    side: str = "right",
) -> VrFrame:
    """Build one VR frame driving a single arm.

    Args:
        grip: The squeeze analog for `side`, in `[0, 1]`.
        validity: The tracking validity of `side` (an INVALID arm withholds its pose).
        position: Controller EE-target position `(x, y, z)` for `side`.
        quaternion: Controller EE-target orientation `(x, y, z, w)` for `side`.
        receive_mono_ns: The PC receive instant in monotonic nanoseconds.
        side: The arm this frame drives (`"left"` or `"right"`).

    Returns:
        (VrFrame) A frame with the other arm left neutral.
    """
    other = "left" if side == "right" else "right"
    world_pose = None if validity is TeleopValidity.INVALID else _world_pose(position, quaternion)
    active = ArmPose(side=side, validity=validity, world_pose=world_pose, grip=grip)
    neutral = ArmPose(
        side=other,
        validity=TeleopValidity.OK,
        world_pose=_world_pose(_ZERO_POSITION, IDENTITY_QUAT),
        grip=0.0,
    )
    teleop_sample = TeleopSample(
        source_ts=receive_mono_ns / 1_000_000_000,
        receive_mono_ns=receive_mono_ns,
        validity=validity,
    )
    return VrFrame(
        teleop_sample=teleop_sample,
        arms={side: active, other: neutral},
        buttons=dict(_NEUTRAL_BUTTONS),
        frame_applied=True,
    )


class StaticPoseSource(PoseSource):
    """A `PoseSource` that serves one preset frame — a test stand-in for a live source.

    It lets the conditioner's `process_source` path be exercised against the real
    `WP-3B-07` `PoseSource` interface without opening a socket.
    """

    def __init__(self, frame: VrFrame | None) -> None:
        """Hold the frame `read_latest` will return (None models "no frame yet")."""
        self._frame = frame

    def set_frame(self, frame: VrFrame | None) -> None:
        """Replace the frame the source will return next."""
        self._frame = frame

    @property
    def frame_applied(self) -> bool:
        """The world-frame transform is already applied (as the UDP source declares)."""
        return True

    def start(self) -> None:
        """No reception to start."""

    def stop(self) -> None:
        """No reception to stop."""

    def read_latest(self) -> VrFrame | None:
        """Return the preset frame without blocking."""
        return self._frame
