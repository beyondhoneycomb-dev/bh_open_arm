"""Pure parsers for the three kernel/iproute2 text surfaces the checks read.

None of these open a socket or shell out — each takes captured text and returns
data, so the same function serves the live path, the synthetic-fixture tests, and
the real-fixture re-verification hook without change. The live capture is done by
the caller (``cat /proc/net/can/rcvlist_all``, ``ss -f link``, ``ip -s link show``);
`06` §5.6 keeps the read side outside these functions so their behaviour is fully
reproducible from a string on any host.

Format notes that are load-bearing:

- ``/proc/net/can/rcvlist_all`` lists one row per receive-all filter. A RAW socket
  bound with its default filter (``can_id`` 0, ``can_mask`` 0) registers exactly one
  such row, so counting rows per device counts receive-all listeners — the number a
  passive ``candump`` increments (kernel ``net/can/proc.c``).
- ``ip -s link show <iface>`` prints a ``TX:`` header line followed by a values line
  whose second field is the TX packet counter (iproute2).
"""

from __future__ import annotations

import re

# The rcvlist header line, printed once by the kernel above the receiver rows.
_RCVLIST_HEADER_TOKEN = "device"
_RCVLIST_IDENT_TOKEN = "ident"

# An interface header line in ``ip link`` output: "3: vcan0: <NOARP,UP,...>" — the
# name may carry an "@parent" suffix on stacked links, so the terminator is [:@].
_IP_LINK_HEADER = re.compile(r"^\s*\d+:\s+(?P<iface>[A-Za-z0-9_.-]+)[:@]")
_TX_HEADER_TOKEN = "TX:"
# Position of the packet counter within the TX values line (bytes, packets, ...).
_TX_PACKETS_FIELD = 1


def parse_rcvlist_all(text: str) -> dict[str, int]:
    """Count receive-all listeners per interface in ``/proc/net/can/rcvlist_all``.

    Args:
        text: Captured contents of the proc file.

    Returns:
        (dict[str, int]) Interface name to number of receive-all registrations.
    """
    counts: dict[str, int] = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if _is_rcvlist_header(fields):
            continue
        iface = fields[0]
        counts[iface] = counts.get(iface, 0) + 1
    return counts


def _is_rcvlist_header(fields: list[str]) -> bool:
    """Report whether a split rcvlist line is the column header rather than a row."""
    return fields[0] == _RCVLIST_HEADER_TOKEN or _RCVLIST_IDENT_TOKEN in fields


def listeners_for(text: str, iface: str) -> int:
    """Return the receive-all listener count for one interface, or 0 if absent.

    Args:
        text: Captured ``/proc/net/can/rcvlist_all`` contents.
        iface: Interface to count.

    Returns:
        (int) Listener rows naming the interface, 0 when it appears in none.
    """
    return parse_rcvlist_all(text).get(iface, 0)


def parse_ss_link(text: str, iface: str) -> int:
    """Count link-layer sockets naming an interface in ``ss -f link`` output.

    This is the coarse fallback the WP names for hosts where ``/proc/net/can`` is
    not mounted. ``ss`` renders CAN sockets less regularly than the proc file, so
    this counts rows whose fields include the interface as a whole token and skips
    the ``Netid``/``State`` header. It is deliberately conservative: it never
    invents a listener, and the proc parser is preferred whenever available.

    Args:
        text: Captured ``ss -f link`` output.
        iface: Interface to count.

    Returns:
        (int) Rows mentioning the interface as a token.
    """
    count = 0
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0] in {"Netid", "State"}:
            continue
        if iface in fields:
            count += 1
    return count


def parse_tx_packets(text: str, iface: str) -> int | None:
    """Read the TX packet counter for an interface from ``ip -s link show``.

    Args:
        text: Captured ``ip -s link show <iface>`` (or all-interface) output.
        iface: Interface whose counter is wanted.

    Returns:
        (int | None) The TX packet counter, or None when the interface or its TX
        values line is not present or not numeric — a read failure the caller must
        not silently treat as zero.
    """
    lines = text.splitlines()
    start = _iface_block_start(lines, iface)
    if start is None:
        return None
    for index in range(start, len(lines)):
        if _IP_LINK_HEADER.match(lines[index]) and index != start:
            return None
        if lines[index].strip().startswith(_TX_HEADER_TOKEN):
            return _tx_packets_after(lines, index)
    return None


def _iface_block_start(lines: list[str], iface: str) -> int | None:
    """Return the index of the interface's header line, or None when absent."""
    for index, line in enumerate(lines):
        match = _IP_LINK_HEADER.match(line)
        if match and match.group("iface") == iface:
            return index
    return None


def _tx_packets_after(lines: list[str], header_index: int) -> int | None:
    """Return the packet counter on the values line following a ``TX:`` header."""
    if header_index + 1 >= len(lines):
        return None
    values = lines[header_index + 1].split()
    if len(values) <= _TX_PACKETS_FIELD or not values[_TX_PACKETS_FIELD].isdigit():
        return None
    return int(values[_TX_PACKETS_FIELD])
