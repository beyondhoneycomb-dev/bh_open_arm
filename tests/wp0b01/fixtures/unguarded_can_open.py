"""Violation fixture: opens an AF_CAN socket with no lock layer in scope.

Proves `staticcheck.find_can_open_without_lock_import` bites — this module is exactly
the out-of-order socket-open acceptance ④ forbids, and the scan must flag it.
"""

from __future__ import annotations

import socket


def open_bus(iface: str) -> socket.socket:
    """Open a raw CAN socket with no lock precondition (the forbidden shape)."""
    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    return sock
