"""Synthetic-but-faithful fixtures of the kernel/iproute2 text the checks parse.

These reproduce the byte layout of ``/proc/net/can/rcvlist_all`` (kernel
``net/can/proc.c``) and ``ip -s link show`` (iproute2) closely enough that the same
parsers serve both these fixtures and, via the re-verification hook, real captures.
They are clearly synthetic: the plan (02a §4.1) treats a parser passing only
synthetic input as unproven against real adapters, which is exactly why the deferred
re-verification hook exists.
"""

from __future__ import annotations

_RCVLIST_HEADER = "  device   can_id   can_mask  function  userdata   matches  ident"
_RCVLIST_ROW = "    {iface}     000    00000000  cbb8c0d0  cbb8c0d0         0  raw"


def make_rcvlist_all(listeners: dict[str, int]) -> str:
    """Render an ``/proc/net/can/rcvlist_all`` capture with the given per-iface counts.

    Args:
        listeners: Interface name to number of receive-all listener rows to emit.

    Returns:
        (str) Header plus one row per listener, terminated by a newline.
    """
    lines = [_RCVLIST_HEADER]
    for iface, count in listeners.items():
        lines.extend(_RCVLIST_ROW.format(iface=iface) for _ in range(count))
    return "\n".join(lines) + "\n"


def make_ip_stats(iface: str, tx_packets: int) -> str:
    """Render an ``ip -s link show <iface>`` capture with a given TX packet count.

    Args:
        iface: Interface the block names.
        tx_packets: Value to place in the TX packet counter field.

    Returns:
        (str) A faithful single-interface ``ip -s link show`` block.
    """
    tx_bytes = tx_packets * 16
    return (
        f"3: {iface}: <NOARP,UP,LOWER_UP> mtu 72 qdisc noqueue state UNKNOWN "
        "mode DEFAULT group default qlen 1000\n"
        "    link/can \n"
        "    RX:  bytes packets errors dropped  missed   mcast\n"
        "             0       0      0       0       0       0\n"
        "    TX:  bytes packets errors dropped carrier collsns\n"
        f"      {tx_bytes:8d} {tx_packets:7d}      0       0       0       0\n"
    )
