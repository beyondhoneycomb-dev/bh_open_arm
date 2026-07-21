"""CAN link verification layer (WP-0B-02) — read-only, never sets the link.

`01` FR-SYS-006 requires the backend to parse `ip -details link show <ch>` before
`Robot.connect()` and refuse startup unless the link is CAN-FD at bitrate 1000000 /
dbitrate 5000000 in the `ERROR-ACTIVE` state. python-can's SocketCAN backend ignores
`bitrate` and acts only on `fd` (`16` §10.1), so a CAN-2.0 link opened `fd=True`
"succeeds" and breaks communication silently (`01` §2.18 trap 5) — this layer is the
guard against that. It is verification only: FR-SYS-006 forbids code from setting the
link, so nothing here runs `ip link set` (`staticcheck.find_link_set_calls` proves the
absence over every line).

Surface:

- `parse_link_show` / `LinkState` — the `{fd, bitrate, dbitrate, state, txqueuelen}`
  parser; unrecognised output raises `UnrecognizedLinkFormatError` rather than passing
  silently.
- `validate_link` / `LinkVerdict` / `LinkMismatch` — the four FR-SYS-006 refusal
  criteria.
- `render_rejection` / `setup_command` — operator guidance naming the exact
  `lerobot-setup-can` command to run.
- `build_setup_artifact` / `SetupArtifact` — the FR-SYS-011 txqueuelen guidance.

The layer imports no CAN stack; it reads text and returns structs.
"""

from __future__ import annotations

from backend.can.link.constants import (
    ACTIVE_STATE,
    BUS_OFF_STATE,
    DEFAULT_TXQUEUELEN,
    RECOMMENDED_TXQUEUELEN,
    REQUIRED_BITRATE,
    REQUIRED_DBITRATE,
    REQUIRED_FD,
)
from backend.can.link.parser import LinkState, UnrecognizedLinkFormatError, parse_link_show
from backend.can.link.reporter import SETUP_COMMAND_PREFIX, render_rejection, setup_command
from backend.can.link.setup_artifact import SetupArtifact, build_setup_artifact
from backend.can.link.validator import LinkMismatch, LinkVerdict, validate_link

__all__ = [
    "ACTIVE_STATE",
    "BUS_OFF_STATE",
    "DEFAULT_TXQUEUELEN",
    "RECOMMENDED_TXQUEUELEN",
    "REQUIRED_BITRATE",
    "REQUIRED_DBITRATE",
    "REQUIRED_FD",
    "SETUP_COMMAND_PREFIX",
    "LinkMismatch",
    "LinkState",
    "LinkVerdict",
    "SetupArtifact",
    "UnrecognizedLinkFormatError",
    "build_setup_artifact",
    "parse_link_show",
    "render_rejection",
    "setup_command",
    "validate_link",
]
