"""Parse `ip -details link show <iface>` output into a verifiable CAN link state.

`01` FR-SYS-006 requires reading each channel's link state before `Robot.connect()` and
refusing startup on a mismatch: python-can's SocketCAN backend takes no
`bitrate`/`data_bitrate` argument (`16` §10.1 — `socketcan.py:694-703`; only `fd`
reaches the socket, `:765-769`), so a link left at CAN 2.0 yet opened `fd=True`
"succeeds" and breaks communication silently (`01` §2.18 trap 5). This module only
reads — it never sets the link, which FR-SYS-006 forbids code from doing.

Acceptance ④ is the load-bearing contract here: output this parser cannot recognise as a
CAN device's detailed link show must raise `UnrecognizedLinkFormatError`, never return a
struct. A silent default on an unknown format is exactly the failure the requirement
names — a format drift that filled a missing field with a passing value would wave a
mis-set link through. Recognition is anchored on the CAN protocol-state line
(`can <flags> state <STATE>`), the one line no non-CAN `ip link show` output carries and
the one place the protocol state lives — distinct from the top line's `state UP`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class UnrecognizedLinkFormatError(ValueError):
    """Output that is not a recognizable `ip -details link show` for a CAN device."""


@dataclass(frozen=True)
class LinkState:
    """The `{fd, bitrate, dbitrate, state, txqueuelen}` struct FR-SYS-006 verifies.

    Attributes:
        iface: Interface the output was read for, carried into the rejection report.
        fd: Whether CAN-FD is enabled on the link.
        bitrate: Nominal (arbitration) bitrate in bit/s, or None when absent.
        dbitrate: Data-phase bitrate in bit/s, or None when the link carries no data
            bittiming (a CAN-2.0 / fd-off link has none).
        state: CAN protocol state token, e.g. `ERROR-ACTIVE` or `BUS-OFF`.
        txqueuelen: Transmit queue length from the top line's `qlen`, or None when the
            output does not print it.
    """

    iface: str
    fd: bool
    bitrate: int | None
    dbitrate: int | None
    state: str
    txqueuelen: int | None


# The CAN detail line: `    can <FD,TDC-AUTO> state ERROR-ACTIVE (berr-counter ...)`.
# Anchored at line start (after indentation) on the bare word `can`, so it matches
# neither the top line (`3: can0: <...>`, starts with a digit) nor the `link/can`
# promiscuity line (starts with `link`). `\b` keeps `candump`-like tokens from matching.
_CAN_LINE = re.compile(r"^[ \t]*can\b.*$", re.MULTILINE)
_CAN_FLAGS = re.compile(r"^[ \t]*can[ \t]+<([^>]*)>")
_STATE = re.compile(r"\bstate[ \t]+([A-Z][A-Z-]*)")
# `\bbitrate` does not match inside `dbitrate` (no word boundary between `d` and `b`),
# so the arbitration and data rates never cross-contaminate.
_BITRATE = re.compile(r"\bbitrate[ \t]+(\d+)")
_DBITRATE = re.compile(r"\bdbitrate[ \t]+(\d+)")
_QLEN = re.compile(r"\bqlen[ \t]+(\d+)")
_FD_TOKEN = re.compile(r"\bfd[ \t]+(on|off)\b")


def parse_link_show(output: str, iface: str) -> LinkState:
    """Parse `ip -details link show <iface>` output into a `LinkState`.

    Args:
        output: Raw text of `ip -details link show <iface>`.
        iface: Interface name, carried into the result for reporting.

    Returns:
        (LinkState) The parsed `{fd, bitrate, dbitrate, state, txqueuelen}` struct.

    Raises:
        UnrecognizedLinkFormatError: If the text carries no CAN protocol-state line, or that
            line carries no state token — i.e. this is not recognizably a CAN device's
            detailed link show. Never returns a struct in that case (acceptance ④).
    """
    can_line_match = _CAN_LINE.search(output)
    if can_line_match is None:
        raise UnrecognizedLinkFormatError(
            f"no CAN protocol-state line in `ip -details link show {iface}` output"
        )
    can_line = can_line_match.group(0)
    state_match = _STATE.search(can_line)
    if state_match is None:
        raise UnrecognizedLinkFormatError(
            f"CAN line carries no state token for {iface}: {can_line.strip()!r}"
        )

    bitrate = _BITRATE.search(output)
    dbitrate = _DBITRATE.search(output)
    qlen = _QLEN.search(output)
    return LinkState(
        iface=iface,
        fd=_detect_fd(output, can_line),
        bitrate=int(bitrate.group(1)) if bitrate else None,
        dbitrate=int(dbitrate.group(1)) if dbitrate else None,
        state=state_match.group(1),
        txqueuelen=int(qlen.group(1)) if qlen else None,
    )


def _detect_fd(output: str, can_line: str) -> bool:
    """Decide whether CAN-FD is enabled from the link show output.

    Two real encodings exist: modern iproute2 prints a `<FD>` flag in the CAN type-flag
    group, while the `lerobot-setup-can` path and some builds emit an explicit
    `fd on`/`fd off` token. An explicit token, when present, is definitive; otherwise
    the `<FD>` flag decides; absent both, the link is CAN 2.0 (fd off).

    Args:
        output: Full link show output (searched for the explicit token).
        can_line: The CAN detail line (searched for the `<FD>` flag).

    Returns:
        (bool) True when CAN-FD is enabled.
    """
    explicit = _FD_TOKEN.search(output)
    if explicit is not None:
        return explicit.group(1) == "on"
    flags = _CAN_FLAGS.search(can_line)
    if flags is not None:
        return "FD" in [token.strip() for token in flags.group(1).split(",")]
    return False
