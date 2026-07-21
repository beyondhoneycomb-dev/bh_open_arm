"""Validate a parsed link state against the FR-SYS-006 startup criteria.

The four refusal criteria are exactly `fd on`, `bitrate 1000000`, `dbitrate 5000000`,
and state `ERROR-ACTIVE` (`≠ BUS-OFF`). `txqueuelen` is deliberately not among them:
FR-SYS-011 makes it a recommendation (priority S) carried in the setup artifact, so a
low queue length is surfaced as an advisory on the verdict but never fails the gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.can.link.constants import (
    ACTIVE_STATE,
    RECOMMENDED_TXQUEUELEN,
    REQUIRED_BITRATE,
    REQUIRED_DBITRATE,
)
from backend.can.link.parser import LinkState


@dataclass(frozen=True)
class LinkMismatch:
    """One failed FR-SYS-006 criterion.

    Attributes:
        field: The struct field that failed (`fd`, `bitrate`, `dbitrate`, `state`).
        expected: Required value as text.
        actual: Observed value as text.
    """

    field: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"{self.field}: expected {self.expected}, got {self.actual}"


@dataclass(frozen=True)
class LinkVerdict:
    """Outcome of verifying one channel's link state.

    Attributes:
        iface: Interface verified.
        ok: True only when every FR-SYS-006 criterion holds.
        mismatches: The failed criteria, empty when ok.
        state: The parsed state the verdict was formed from.
        txqueuelen_below_recommended: FR-SYS-011 advisory; never affects `ok`.
    """

    iface: str
    ok: bool
    mismatches: tuple[LinkMismatch, ...]
    state: LinkState
    txqueuelen_below_recommended: bool


def validate_link(state: LinkState) -> LinkVerdict:
    """Verify a parsed link state against the four FR-SYS-006 refusal criteria.

    Args:
        state: Parsed link state.

    Returns:
        (LinkVerdict) `ok` true only when fd is on, the bitrate and dbitrate match the
        required rates, and the bus state is `ERROR-ACTIVE`. A `BUS-OFF` (or any other
        non-active) state is a state mismatch. A below-recommended txqueuelen is flagged
        as an advisory but does not affect `ok`.
    """
    mismatches: list[LinkMismatch] = []
    if not state.fd:
        mismatches.append(LinkMismatch("fd", "on", "off"))
    if state.bitrate != REQUIRED_BITRATE:
        mismatches.append(LinkMismatch("bitrate", str(REQUIRED_BITRATE), str(state.bitrate)))
    if state.dbitrate != REQUIRED_DBITRATE:
        mismatches.append(LinkMismatch("dbitrate", str(REQUIRED_DBITRATE), str(state.dbitrate)))
    if state.state != ACTIVE_STATE:
        mismatches.append(LinkMismatch("state", ACTIVE_STATE, state.state))

    below = state.txqueuelen is not None and state.txqueuelen < RECOMMENDED_TXQUEUELEN
    return LinkVerdict(
        iface=state.iface,
        ok=not mismatches,
        mismatches=tuple(mismatches),
        state=state,
        txqueuelen_below_recommended=below,
    )
