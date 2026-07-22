"""WebXR fallback pose path — HTTPS/WSS:8443 immersive-ar controller input (WP-3B-08).

The negative-branch path of `PG-VR-001` (`02b` §6.1/§6.2): when the Quest APK cannot
be sided-loaded, the teleoperator falls back to a WebXR browser session. This package
is that path, and it exists precisely so the fallback is real, not aspirational. It
fixes the four upstream `ar.js`/`main.py` defects the port must repair (`05` §2.7):

- profiles are resolved by a FALLBACK CHAIN or the `xr-standard` mapping, never an
  exact-string whitelist — an unknown headset is admitted, so a profile mismatch
  cannot dark the whole teleop path (`profiles`, `FR-TEL-017`);
- `buttons[1]` (squeeze/grip) is read as an analog value — the clutch's input
  (`gamepad.read_squeeze`, `FR-TEL-018`);
- the joystick is guarded on `axes.length >= 4` and read from `axes[2]/[3]`, never
  falsy-gated on axis values (`gamepad.read_thumbstick`, `FR-TEL-019`);
- single-arm sessions are admitted — a right-only or left-only mode begins with one
  input source (`session`, `FR-TEL-020`).

The HTTPS/WSS endpoint (`tls`, default port 8443, `FR-TEL-015`) and the full
`session.inputSources[*].profiles` logging at begin (`session`, `FR-TEL-016`) round
out the offline surface. The live `immersive-ar` session needs a headset browser and
is deferred to the real-fixture re-verification hook (`reverify`, plan 02a §4.1).

The tracking validity and the dual timestamps are consumed from the frozen
`CTR-TEL@v1`/`CTR-PRIM@v1` contracts by reference and never restated (`02b` §5.0b).
"""

from __future__ import annotations

from backend.teleop.webxr.gamepad import (
    FaceButtons,
    GamepadState,
    Thumbstick,
    read_face_buttons,
    read_squeeze,
    read_thumbstick,
    read_trigger,
    thumbstick_transmittable,
)
from backend.teleop.webxr.profiles import (
    XR_STANDARD_LAYOUT,
    ControllerLayout,
    ProfileResolution,
    ProfileResolutionError,
    ResolvedVia,
    chain_match,
    is_resolvable,
    resolve_layout,
)
from backend.teleop.webxr.reverify import (
    ArmReverify,
    WebXrReverifyReport,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.teleop.webxr.session import (
    Handedness,
    ImmersiveArSession,
    InputSource,
    SessionConfig,
    SessionError,
    TeleopMode,
)
from backend.teleop.webxr.source import GripPose, WebXrArmSample, WebXrPoseSource
from backend.teleop.webxr.tls import TlsConfig, TlsConfigError, tls_config

__all__ = [
    "XR_STANDARD_LAYOUT",
    "ArmReverify",
    "ControllerLayout",
    "FaceButtons",
    "GamepadState",
    "GripPose",
    "Handedness",
    "ImmersiveArSession",
    "InputSource",
    "ProfileResolution",
    "ProfileResolutionError",
    "ResolvedVia",
    "SessionConfig",
    "SessionError",
    "TeleopMode",
    "Thumbstick",
    "TlsConfig",
    "TlsConfigError",
    "WebXrArmSample",
    "WebXrPoseSource",
    "WebXrReverifyReport",
    "chain_match",
    "fixture_dir_from_env",
    "is_resolvable",
    "read_face_buttons",
    "read_squeeze",
    "read_thumbstick",
    "read_trigger",
    "resolve_layout",
    "reverify_from_fixture",
    "thumbstick_transmittable",
    "tls_config",
]
