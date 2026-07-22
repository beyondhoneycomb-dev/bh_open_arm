"""Real-headset boundary and its re-verification hook (`02a` §4.1, the ONE RULE).

Everything else in this package runs here on the frozen synthetic stream. What
cannot run on this host is a *real Meta Quest*: the APK pose stream needs a headset
worn by a person, and Quest 3S APK viability is itself an open gate (`PG-VR-001`,
`16` M-22). So a bound real test SKIPs with a reason rather than asserting a green
that no headset produced.

`replay_from_capture` is what the deferral must ship: given a file of datagrams
captured off a real headset, it re-runs the *identical* `parse_datagram` — the same
transform chain, the same dual-timestamp preservation, the same validity model —
over the real bytes. No parse path is re-implemented for hardware; the real capture
simply flows through the production parser.

The capture file is newline-terminated UTF-8 JSON datagrams, exactly what the APK
streams to `:5006` (one frame per line).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from backend.teleop.vr_udp.constants import TEXT_ENCODING
from backend.teleop.vr_udp.frame import VrFrame
from backend.teleop.vr_udp.protocol import FrameParseError, parse_datagram

# A rig points the hook at a directory or file of real captured datagrams. Distinct
# from the sensing hook's variable so a rig can aim the two harnesses separately.
REAL_FIXTURE_ENV_VAR = "OPENARM_VR_REAL_FIXTURE"

# The capture file name looked for when the variable names a directory.
CAPTURE_FILENAME = "vr_pose_capture.jsonl"


def real_vr_supported() -> tuple[bool, str]:
    """Report whether a real-headset re-verification can run here, and why not.

    There is no Quest on this host, so support means a real capture has been
    supplied through `REAL_FIXTURE_ENV_VAR`. When absent, the reason says so — a
    skip must carry why, never fabricate a pass.

    Returns:
        (tuple[bool, str]) `(supported, reason)`; reason is empty when supported.
    """
    capture = capture_path_from_env()
    if capture is None:
        return (
            False,
            "no Meta Quest APK pose stream on this host and no real capture at "
            f"{REAL_FIXTURE_ENV_VAR}; real headset verification is deferred (PG-VR-001)",
        )
    return (True, "")


def capture_path_from_env() -> Path | None:
    """Return the real-capture file named by the environment, if present.

    Accepts either a direct file path or a directory holding `CAPTURE_FILENAME`.

    Returns:
        (Path | None) The capture file, or None when unset or missing.
    """
    raw = os.environ.get(REAL_FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    if path.is_dir():
        candidate = path / CAPTURE_FILENAME
        return candidate if candidate.is_file() else None
    return path if path.is_file() else None


def replay_from_capture(capture_path: Path) -> list[VrFrame]:
    """Re-run the production parser over a file of real captured datagrams.

    Each line is one datagram, parsed by the same `parse_datagram` the socket
    thread uses. The receive instant is stamped from this host's monotonic clock at
    replay time, so both timestamps stay distinct exactly as on the live path.

    Args:
        capture_path: A file of newline-terminated UTF-8 JSON datagrams.

    Returns:
        (list[VrFrame]) The frames parsed from the real capture, in order.

    Raises:
        FrameParseError: If a captured line is not a well-formed VR pose frame —
            surfaced, not swallowed, so a corrupt real capture is visible.
    """
    frames: list[VrFrame] = []
    for line in capture_path.read_text(encoding=TEXT_ENCODING).splitlines():
        if not line.strip():
            continue
        frame = parse_datagram(line.encode(TEXT_ENCODING), time.monotonic_ns())
        frames.append(frame)
    return frames


# Re-exported so a caller can distinguish a corrupt real capture from an empty one.
__all__ = [
    "CAPTURE_FILENAME",
    "REAL_FIXTURE_ENV_VAR",
    "FrameParseError",
    "capture_path_from_env",
    "real_vr_supported",
    "replay_from_capture",
]
