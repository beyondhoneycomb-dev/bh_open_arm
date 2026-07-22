"""Real-fixture re-verification hook (plan 02a §4.1) for the WebXR path (WP-3B-08).

The offline half of this WP runs here on synthetic controllers: profile resolution,
the `buttons[1]` squeeze read, the `axes.length >= 4` joystick guard and single-arm
admission are pure functions over reported profile strings and gamepad arrays, so a
synthetic input source and a real Quest 3S run through identical code. What cannot
run here is those same functions over a REAL headset's reported values — the Quest
3S profile strings are unconfirmed (`05` §5 U-6) and there is no headset browser on
this host, so the live `immersive-ar` session is deferred.

This hook is what the deferral ships. When a directory holding one real captured
session is supplied (via `OPENARM_WEBXR_REAL_FIXTURE`), `reverify_from_fixture`
re-runs the identical resolver, gamepad reads and session admission against the real
reported strings and arrays; until then the bound test skips with a reason. The point
is that no path is re-implemented for hardware — the fallback chain that admits an
unknown profile offline is the exact one that must admit the real Quest 3S. The
fixture directory holds `session.json`:

    {
      "mode": "bimanual",
      "input_sources": [
        {"handedness": "right", "profiles": [...], "mapping": "xr-standard",
         "buttons": [...], "axes": [...]},
        ...
      ]
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.teleop.webxr.constants import DEFAULT_TLS_HOST, DEFAULT_TLS_PORT
from backend.teleop.webxr.gamepad import GamepadState, read_squeeze, thumbstick_transmittable
from backend.teleop.webxr.profiles import ResolvedVia, resolve_layout
from backend.teleop.webxr.session import (
    Handedness,
    ImmersiveArSession,
    InputSource,
    SessionConfig,
    TeleopMode,
)
from backend.teleop.webxr.tls import TlsConfig

FIXTURE_ENV_VAR = "OPENARM_WEBXR_REAL_FIXTURE"
SESSION_FILENAME = "session.json"

# Placeholder TLS material for the offline replay: the hook re-verifies profile and
# gamepad resolution against real reported strings, not the certificate bytes, so a
# non-empty path pair satisfies the config without needing real key material on disk.
_REPLAY_CERTIFICATE_PATH = Path("webxr-cert.pem")
_REPLAY_KEY_PATH = Path("webxr-key.pem")


@dataclass(frozen=True)
class ArmReverify:
    """The re-derived resolution of one real input source.

    Attributes:
        handedness: The arm the source drives.
        resolved_via: Whether the fallback chain or the xr-standard mapping resolved it.
        matched_profile: The profile string (or mapping token) that resolved it.
        squeeze: The `buttons[1]` squeeze value read from the real gamepad array.
        thumbstick_transmittable: Whether the real gamepad cleared the axis-count guard.
    """

    handedness: Handedness
    resolved_via: ResolvedVia
    matched_profile: str
    squeeze: float
    thumbstick_transmittable: bool


@dataclass(frozen=True)
class WebXrReverifyReport:
    """The result of re-running the WebXR resolution over one real captured session.

    Attributes:
        mode: The teleop mode the capture declared.
        arms: Per-arm re-derived resolution, in the session's active-side order.
    """

    mode: TeleopMode
    arms: tuple[ArmReverify, ...]


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present."""
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _input_source(spec: Any) -> InputSource:
    """Build one input source from its decoded-JSON fixture record.

    The record is untyped decoded JSON, so it is read as `Any` and coerced field by
    field into the typed `InputSource` the offline path expects.
    """
    buttons = [float(value) for value in spec.get("buttons", [])]
    axes = [float(value) for value in spec.get("axes", [])]
    profiles = [str(profile) for profile in spec.get("profiles", [])]
    return InputSource(
        handedness=Handedness(str(spec["handedness"])),
        profiles=profiles,
        gamepad=GamepadState(buttons=buttons, axes=axes, mapping=str(spec.get("mapping", ""))),
    )


def reverify_from_fixture(fixture_dir: Path) -> WebXrReverifyReport:
    """Re-run WebXR profile and gamepad resolution against a real captured session.

    Every computation is the one the synthetic tests exercise, pointed at real
    reported strings and arrays — the hook re-implements nothing for hardware.

    Args:
        fixture_dir: Directory holding `session.json` (see the module docstring).

    Returns:
        (WebXrReverifyReport) Per-arm resolution under the real reported values.

    Raises:
        FileNotFoundError: If `session.json` is absent.
    """
    session_path = fixture_dir / SESSION_FILENAME
    if not session_path.is_file():
        raise FileNotFoundError(f"missing {SESSION_FILENAME} in {fixture_dir}")
    spec = json.loads(session_path.read_text(encoding="utf-8"))

    mode = TeleopMode(str(spec["mode"]))
    sources = [_input_source(record) for record in spec["input_sources"]]

    config = SessionConfig(
        mode=mode,
        tls=TlsConfig(
            certificate_path=_REPLAY_CERTIFICATE_PATH,
            key_path=_REPLAY_KEY_PATH,
            host=DEFAULT_TLS_HOST,
            port=DEFAULT_TLS_PORT,
        ),
    )
    session = ImmersiveArSession(config)
    session.begin(sources)

    by_side = {source.handedness: source for source in sources}
    arms: list[ArmReverify] = []
    for side in mode.active_sides:
        source = by_side[side]
        resolution = resolve_layout(source.profiles, source.gamepad.mapping)
        arms.append(
            ArmReverify(
                handedness=side,
                resolved_via=resolution.via,
                matched_profile=resolution.matched_profile,
                squeeze=read_squeeze(source.gamepad, resolution.layout),
                thumbstick_transmittable=thumbstick_transmittable(source.gamepad),
            )
        )
    return WebXrReverifyReport(mode=mode, arms=tuple(arms))
