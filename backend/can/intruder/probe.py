"""Host capability probes that gate the deferred, live-vcan acceptance items.

The synthetic-fixture acceptance (④, ⑤) runs on any host because it feeds captured
text to pure checks. The injection acceptance (①, ②, ③) needs a real CAN interface to
bind sockets to, which this dev host does not have and cannot create. These probes
let the deferred tests skip *with a reason* instead of failing or, worse, pretending
to pass: a test guards on `vcan_available` and states in its skip reason that a vcan
is required.
"""

from __future__ import annotations

from pathlib import Path

# ARPHRD_CAN — the value ``/sys/class/net/<iface>/type`` holds for a CAN link,
# virtual (vcan) or physical. Distinguishes a CAN interface from ethernet (1).
ARPHRD_CAN = 280

_NET_CLASS_DIR = Path("/sys/class/net")


def can_interfaces() -> tuple[str, ...]:
    """List CAN interfaces present on the host, virtual or physical.

    Returns:
        (tuple[str, ...]) Interface names whose link type is ARPHRD_CAN, sorted.
        Empty on a host with no CAN interface (this dev desktop).
    """
    if not _NET_CLASS_DIR.is_dir():
        return ()
    found: list[str] = []
    for entry in sorted(_NET_CLASS_DIR.iterdir()):
        type_file = entry / "type"
        if not type_file.is_file():
            continue
        try:
            link_type = int(type_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if link_type == ARPHRD_CAN:
            found.append(entry.name)
    return tuple(found)


def vcan_available(iface: str) -> bool:
    """Report whether a named CAN interface exists and can be bound to.

    Args:
        iface: Interface name a live injection test would use.

    Returns:
        (bool) True when the interface is present and of CAN type.
    """
    return iface in can_interfaces()
