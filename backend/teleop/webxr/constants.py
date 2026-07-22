"""Named constants for the WebXR fallback pose path (WP-3B-08).

Every literal the session, profile, gamepad and TLS layers key on lives here so a
WebXR default is changed in one place and never restated at a call site. Two groups
carry meaning that is not local to the line that uses them, so both are named:

- the `xr-standard` gamepad button/axis indices (`05` §2.7, W3C WebXR Gamepads
  Module) — `buttons[1]` being the squeeze and `axes[2]/[3]` being the thumbstick
  are the whole point of the WP, and a bare `1`/`2`/`3` at a read site would hide it;
- the transport defaults — WebXR forces HTTPS, so port `8443` and the `immersive-ar`
  session mode are contract facts (`FR-TEL-015`), not tunables a call site invents.
"""

from __future__ import annotations

# The XR session mode this path requests. WebXR forces an immersive session for
# controller input; `immersive-ar` is the one this path opens (`05` §2.7 path B,
# `ar.js:189,193`, `FR-TEL-015`).
SESSION_MODE = "immersive-ar"

# The reference spaces a session may request. `viewer` is the upstream default (the
# origin follows the head); `local-floor` is the immersive/ego choice (`05` §2.7,
# `FR-TEL-075`). The default is preserved from upstream and overridable per session.
REFERENCE_SPACE_VIEWER = "viewer"
REFERENCE_SPACE_LOCAL = "local"
REFERENCE_SPACE_LOCAL_FLOOR = "local-floor"
REFERENCE_SPACES = (REFERENCE_SPACE_VIEWER, REFERENCE_SPACE_LOCAL, REFERENCE_SPACE_LOCAL_FLOOR)
REFERENCE_SPACE_DEFAULT = REFERENCE_SPACE_VIEWER

# The input-source space a pose is read from. `gripSpace` is the controller grip pose
# (the upstream default, `ar.js:107`); `targetRaySpace` is the pointing ray. Named so
# the pose-source choice is explicit rather than a stray string.
POSE_SPACE_GRIP = "gripSpace"
POSE_SPACE_TARGET_RAY = "targetRaySpace"
POSE_SPACES = (POSE_SPACE_GRIP, POSE_SPACE_TARGET_RAY)
POSE_SPACE_DEFAULT = POSE_SPACE_GRIP

# The HTTPS/WSS transport. WebXR is served over TLS only; the host binds all
# interfaces and the port is the spec default (`05` section 2.7 path B, the WebXR
# host/port config row, `FR-TEL-015`).
DEFAULT_TLS_HOST = "0.0.0.0"
DEFAULT_TLS_PORT = 8443

# The `xr-standard` gamepad layout indices (`05` §2.7 registry note, W3C WebXR
# Gamepads Module). Every profile in the fallback chain maps to this same layout, so
# the indices are the layout, not per-profile data:
#   buttons[0] = trigger, buttons[1] = squeeze/grip,
#   buttons[4]/[5] = A·B or X·Y, axes[2]/[3] = thumbstick x/y.
XR_STANDARD_TRIGGER_BUTTON_INDEX = 0
XR_STANDARD_SQUEEZE_BUTTON_INDEX = 1
XR_STANDARD_PRIMARY_FACE_BUTTON_INDEX = 4
XR_STANDARD_SECONDARY_FACE_BUTTON_INDEX = 5
XR_STANDARD_THUMBSTICK_X_AXIS_INDEX = 2
XR_STANDARD_THUMBSTICK_Y_AXIS_INDEX = 3

# The joystick send guard (`FR-TEL-019`, `05` §2.7 ⓒ). The thumbstick lives at
# `axes[2]/[3]`, so the gamepad must expose at least four axes for those indices to
# exist. The guard is on the axis COUNT — never on the axis VALUES: the upstream
# `if (axes[0] && axes[1] && axes[2] && axes[3])` guard is falsy-gated on values that
# are legitimately zero (Touch Plus has no touchpad, so `axes[0]/[1]` are always 0),
# which is why the upstream joystick is never transmitted.
MIN_AXES_FOR_THUMBSTICK = 4

# The gamepad `mapping` string a controller reports when its buttons and axes follow
# the `xr-standard` layout. Resolving a controller by this — rather than by an exact
# profile-string match — is what lets an unknown headset work (`FR-TEL-017`).
XR_STANDARD_MAPPING = "xr-standard"

# The controller profile fallback chain (`FR-TEL-017`, `05` §2.7 ⓐ). These are
# ordered most-specific to least-specific and all resolve to the `xr-standard`
# layout; the last entry is the generic profile the WebXR input-profiles registry
# guarantees as a floor. This is a PREFERENCE ORDER, not a whitelist: a profile
# string absent from this chain is NOT rejected — it falls through to the
# `xr-standard` mapping check, which is the branch that keeps an unknown Quest 3S
# (its reported profile string is unconfirmed, `05` section 5 U-6) from causing a
# total teleop outage.
FALLBACK_PROFILE_CHAIN = (
    "meta-quest-touch-plus",
    "meta-quest-touch-plus-v2",
    "oculus-touch-v3",
    "generic-trigger-squeeze-thumbstick",
)

# The analog range of a WebXR gamepad button `.value` and of an axis reading. Buttons
# are `[0, 1]`; axes are `[-1, 1]`. Named so a clamp or a bounds check states intent.
ANALOG_BUTTON_MIN = 0.0
ANALOG_BUTTON_MAX = 1.0
AXIS_MIN = -1.0
AXIS_MAX = 1.0
