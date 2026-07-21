"""Pass fixture: opens an AF_CAN socket only behind the lock guard.

Proves the scan does not over-fire: the same socket-open is legitimate when the lock
layer is imported and the open is routed through `guarded_connect`, so this module
must produce no finding.
"""

from __future__ import annotations

import socket

from backend.can.lock import LockManager, guarded_connect


def open_bus(manager: LockManager, iface: str) -> socket.socket:
    """Open a raw CAN socket, but only after the channel lock is held."""

    def _open() -> socket.socket:
        sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        sock.bind((iface,))
        return sock

    return guarded_connect(manager, [iface], _open)
