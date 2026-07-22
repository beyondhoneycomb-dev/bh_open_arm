"""Shared builders for the WP-3B-08 WebXR tests.

These construct xr-standard gamepads, input sources and begun sessions so each test
states only the fact it exercises. A helper also maps a synthetic VR sample's grip to
a WebXR squeeze, so the WebXR source can be driven off the same deterministic stream
the UDP path uses (`contracts.fixtures.vr_pose_stream`).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from backend.teleop.webxr.constants import XR_STANDARD_MAPPING
from backend.teleop.webxr.gamepad import GamepadState
from backend.teleop.webxr.session import (
    Handedness,
    ImmersiveArSession,
    InputSource,
    SessionConfig,
    TeleopMode,
)
from backend.teleop.webxr.source import GripPose
from backend.teleop.webxr.tls import TlsConfig, tls_config
from contracts.fixtures.vr_pose_stream import VrPoseSample

# A Quest 3S reports a profile string that is not yet confirmed (`05` §5 U-6); this
# stands in for "an unknown headset" — a string that is in no fallback-chain entry.
UNKNOWN_QUEST_PROFILE = "meta-quest-3s-unconfirmed"


def xr_standard_gamepad(
    squeeze: float = 0.0,
    trigger: float = 0.0,
    thumbstick: tuple[float, float] = (0.0, 0.0),
    primary: float = 0.0,
    secondary: float = 0.0,
) -> GamepadState:
    """Build a full xr-standard gamepad with named values at their layout indices."""
    buttons = [0.0] * 6
    buttons[0] = trigger
    buttons[1] = squeeze
    buttons[4] = primary
    buttons[5] = secondary
    axes = [0.0, 0.0, thumbstick[0], thumbstick[1]]
    return GamepadState(buttons=buttons, axes=axes, mapping=XR_STANDARD_MAPPING)


def input_source(
    handedness: Handedness,
    profiles: Sequence[str] = (UNKNOWN_QUEST_PROFILE,),
    gamepad: GamepadState | None = None,
) -> InputSource:
    """Build one input source, defaulting to an unknown-profile xr-standard controller."""
    return InputSource(
        handedness=handedness,
        profiles=list(profiles),
        gamepad=gamepad if gamepad is not None else xr_standard_gamepad(),
    )


def tls(tmp_path: Path) -> TlsConfig:
    """Build a valid TLS config rooted in a tmp dir (paths need not exist to construct)."""
    return tls_config(tmp_path / "cert.pem", tmp_path / "key.pem")


def session(mode: TeleopMode, tmp_path: Path) -> ImmersiveArSession:
    """Build an unbegun session for a mode with a valid TLS endpoint."""
    return ImmersiveArSession(SessionConfig(mode=mode, tls=tls(tmp_path)))


def grip_from_sample(sample: VrPoseSample, side: str) -> GripPose:
    """Map one arm of a synthetic VR sample to a WebXR world-frame grip pose."""
    px, py, pz = sample.positions[side]
    qx, qy, qz, qw = sample.quaternions[side]
    return GripPose(position=(px, py, pz), orientation=(qw, qx, qy, qz))


def gamepad_from_sample(sample: VrPoseSample, side: str) -> GamepadState:
    """Map one arm of a synthetic VR sample to a WebXR gamepad (grip -> squeeze)."""
    return xr_standard_gamepad(squeeze=sample.grips[side])
