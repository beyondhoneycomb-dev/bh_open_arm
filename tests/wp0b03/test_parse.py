"""Parser tests: the three kernel/iproute2 surfaces read correctly, and fail loudly.

These back the WARN/FAULT checks above them. A parser that silently returns zero for
an unreadable TX counter would let a real second writer pass, so the "unknown format
is an error, not a pass" property (mirrored from WP-0B-02) is asserted here.
"""

from __future__ import annotations

from backend.can.intruder.parse import (
    listeners_for,
    parse_rcvlist_all,
    parse_ss_link,
    parse_tx_packets,
)
from tests.wp0b03.synth import make_ip_stats, make_rcvlist_all


def test_rcvlist_counts_listeners_per_iface() -> None:
    """Each receive-all row is counted, per interface, header excluded."""
    text = make_rcvlist_all({"vcan0": 3, "vcan1": 1})
    assert parse_rcvlist_all(text) == {"vcan0": 3, "vcan1": 1}
    assert listeners_for(text, "vcan0") == 3


def test_rcvlist_absent_iface_is_zero_not_error() -> None:
    """An interface with no listener row counts as zero, not a missing key."""
    text = make_rcvlist_all({"vcan0": 1})
    assert listeners_for(text, "vcan9") == 0


def test_rcvlist_header_only_is_empty() -> None:
    """A file with only the header (no receivers) yields no counts."""
    text = make_rcvlist_all({})
    assert parse_rcvlist_all(text) == {}


def test_tx_packets_read_from_ip_stats() -> None:
    """The TX packet counter is the second field of the values line under ``TX:``."""
    assert parse_tx_packets(make_ip_stats("vcan0", 4210), "vcan0") == 4210


def test_tx_packets_absent_iface_is_none() -> None:
    """A counter that is not present is None — an unreadable measurement, not zero."""
    assert parse_tx_packets(make_ip_stats("vcan0", 5), "can3") is None


def test_tx_packets_scopes_to_named_iface() -> None:
    """With two interface blocks, the counter for the named one is returned."""
    two = make_ip_stats("vcan0", 11) + make_ip_stats("vcan1", 22)
    assert parse_tx_packets(two, "vcan0") == 11
    assert parse_tx_packets(two, "vcan1") == 22


def test_ss_link_fallback_counts_iface_tokens() -> None:
    """The coarse ``ss`` fallback counts rows naming the interface, skipping header."""
    text = (
        "Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
        "p_raw UNCONN 0 0 vcan0 *\n"
        "p_raw UNCONN 0 0 vcan0 *\n"
    )
    assert parse_ss_link(text, "vcan0") == 2
    assert parse_ss_link(text, "vcan1") == 0
