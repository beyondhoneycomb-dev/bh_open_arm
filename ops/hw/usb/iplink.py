"""Parser for `ip -s -d link show <iface>` CAN bus statistics.

`15` NFR-PRF-046 and `WP-0B-06` acceptance ④ require the bus statistics —
error counters and restarts — to be recorded *alongside* the `f_max_can` sweep, as
an independent check that a high achieved rate was not bought with a rising error
rate. This module extracts those counters from the `ip -s -d link show` output.

It is a text parser with no dependency on any CAN library, so it runs on synthetic
fixtures here; the real adapter's exact field spacing is confirmed by the
re-verification hook against a captured `ip -s -d` dump.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The CAN detail line: `can state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 100`.
_CAN_STATE = re.compile(
    r"can\s+state\s+(?P<state>\S+)\s+\(berr-counter\s+tx\s+(?P<btx>\d+)\s+rx\s+(?P<brx>\d+)\)"
    r"(?:\s+restart-ms\s+(?P<restart_ms>\d+))?"
)
# The CAN error-counter header and its value row (`re-started bus-errors arbit-lost
# error-warn error-pass bus-off` then six integers).
_ERR_HEADER = re.compile(
    r"re-started\s+bus-errors\s+arbit-lost\s+error-warn\s+error-pass\s+bus-off"
)
_SIX_INTS = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
# RX/TX summary rows under the standard `-s` statistics block.
_RX_HEADER = re.compile(r"^\s*RX:\s")
_TX_HEADER = re.compile(r"^\s*TX:\s")
_LEADING_INTS = re.compile(r"^\s*(\d+)\s+(\d+)")


@dataclass(frozen=True)
class CanBusStats:
    """Bus statistics for one CAN interface, as `ip -s -d link show` reports them.

    Every counter is optional because a fixture (or a kernel that omits a field)
    may not carry it; None means "not reported", distinct from a reported 0.

    Attributes:
        iface: The interface these stats belong to.
        state: CAN controller state, e.g. "ERROR-ACTIVE" / "BUS-OFF".
        berr_tx: Bus-error counter, TX side.
        berr_rx: Bus-error counter, RX side.
        restart_ms: Configured auto-restart delay.
        restarts: Number of bus-off auto-restarts observed.
        bus_errors: Bus-error events counter.
        error_warn: Error-warning transitions.
        error_pass: Error-passive transitions.
        bus_off: Bus-off transitions.
        rx_packets: Frames received.
        tx_packets: Frames transmitted.
    """

    iface: str
    state: str | None
    berr_tx: int | None
    berr_rx: int | None
    restart_ms: int | None
    restarts: int | None
    bus_errors: int | None
    error_warn: int | None
    error_pass: int | None
    bus_off: int | None
    rx_packets: int | None
    tx_packets: int | None

    def as_dict(self) -> dict[str, object]:
        """Project to a JSON-serialisable mapping for the artifact.

        Returns:
            (dict[str, object]) The bus statistics as plain data.
        """
        return {
            "iface": self.iface,
            "state": self.state,
            "berr_counter": {"tx": self.berr_tx, "rx": self.berr_rx},
            "restart_ms": self.restart_ms,
            "restarts": self.restarts,
            "bus_errors": self.bus_errors,
            "error_warn": self.error_warn,
            "error_pass": self.error_pass,
            "bus_off": self.bus_off,
            "rx_packets": self.rx_packets,
            "tx_packets": self.tx_packets,
        }


def parse_bus_stats(iface: str, ip_output: str) -> CanBusStats:
    """Extract CAN bus statistics from one interface's `ip -s -d link show` output.

    Args:
        iface: The interface the output describes (recorded on the result).
        ip_output: Raw `ip -s -d link show <iface>` text.

    Returns:
        (CanBusStats) The parsed statistics; unreported fields are None.
    """
    state = berr_tx = berr_rx = restart_ms = None
    restarts = bus_errors = error_warn = error_pass = bus_off = None
    rx_packets = tx_packets = None

    lines = ip_output.splitlines()
    for index, line in enumerate(lines):
        state_match = _CAN_STATE.search(line)
        if state_match:
            state = state_match.group("state")
            berr_tx = int(state_match.group("btx"))
            berr_rx = int(state_match.group("brx"))
            if state_match.group("restart_ms") is not None:
                restart_ms = int(state_match.group("restart_ms"))

        if _ERR_HEADER.search(line):
            values = _next_six_ints(lines, index + 1)
            if values is not None:
                restarts, bus_errors, _arbit, error_warn, error_pass, bus_off = values

        if _RX_HEADER.search(line):
            rx_packets = _second_int(lines, index + 1)
        if _TX_HEADER.search(line):
            tx_packets = _second_int(lines, index + 1)

    return CanBusStats(
        iface=iface,
        state=state,
        berr_tx=berr_tx,
        berr_rx=berr_rx,
        restart_ms=restart_ms,
        restarts=restarts,
        bus_errors=bus_errors,
        error_warn=error_warn,
        error_pass=error_pass,
        bus_off=bus_off,
        rx_packets=rx_packets,
        tx_packets=tx_packets,
    )


def _next_six_ints(lines: list[str], start: int) -> tuple[int, ...] | None:
    """Return the six integers on the first matching row at or after `start`."""
    for line in lines[start : start + 2]:
        match = _SIX_INTS.match(line)
        if match:
            return tuple(int(group) for group in match.groups())
    return None


def _second_int(lines: list[str], start: int) -> int | None:
    """Return the second integer (packet count) on the values row after an RX/TX header.

    The `-s` block prints a header then a values row `bytes packets errors ...`; the
    packet count is the second integer on that row.
    """
    for line in lines[start : start + 2]:
        match = _LEADING_INTS.match(line)
        if match:
            return int(match.group(2))
    return None
