"""Fixed identities and destinations for the CAN bring-up units (WP-OPS-02).

The link parameters are deliberately not redeclared here: `BITRATE`, `DBITRATE` and
`TXQUEUELEN` are imported from `backend.can.link.constants`, the single home for the
`01` FR-SYS-006 / FR-SYS-011 values the backend verifies. The unit this package renders
sets exactly what the backend checks, so sharing one constant is what makes "unit set"
and "backend verified" impossible to drift apart — a second copy could set a value the
backend would then refuse.

The four fixed interface names come from `ops.hw.udev.rules.CONTRACT_NAMES` (WP-0B-05,
`02` FR-CON-005) for the same reason: the setup unit brings up the very names the udev
rule assigns, never a private duplicate list.
"""

from __future__ import annotations

from backend.can.link.constants import (
    RECOMMENDED_TXQUEUELEN,
    REQUIRED_BITRATE,
    REQUIRED_DBITRATE,
)
from ops.hw.udev.rules import CONTRACT_NAMES

# FR-SYS-006/011 link parameters the unit sets and the backend verifies, re-exported
# under bring-up names so this package reads as one story without hiding their origin.
LINK_BITRATE = REQUIRED_BITRATE
LINK_DBITRATE = REQUIRED_DBITRATE
LINK_TXQUEUELEN = RECOMMENDED_TXQUEUELEN

# The four fixed channels, in bring-up order (`02` FR-CON-005). Consumed from WP-0B-05.
INTERFACE_NAMES = CONTRACT_NAMES

# systemd unit identities. The link unit sets the link; the backend unit is gated on it.
CAN_LINK_UNIT = "openarm-can-link.service"
BACKEND_UNIT = "openarm-backend.service"
# The name-assignment step the link setup must run after: fixed names must exist as
# interfaces before `ip link set <name>` can address them (`01` FR-SYS-008 precedes 006).
UDEV_SETTLE_UNIT = "systemd-udev-settle.service"

# Install destinations. The operator materializes these on the target host; FR-SYS-006
# forbids code from performing the bring-up itself, so this package renders the files and
# the install helper stages them, but systemd — not Python — runs the `ip link` commands.
UDEV_RULES_DEST = "/etc/udev/rules.d/80-openarm-can.rules"
UNIT_INSTALL_DIR = "/etc/systemd/system"
