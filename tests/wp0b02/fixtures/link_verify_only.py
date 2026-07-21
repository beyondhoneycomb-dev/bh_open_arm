"""Pass fixture: returns setup guidance as data, never sets the link.

Proves the scan does not over-fire — the setup artifact legitimately carries the
`ip link set … txqueuelen` command as a string for the operator, and a returned string
is inert data, not a link mutation. This module must produce no finding.
"""

from __future__ import annotations


def setup_hint(iface: str) -> str:
    """Return the operator command as data — the backend never runs it."""
    return f"ip link set {iface} txqueuelen 1000"
