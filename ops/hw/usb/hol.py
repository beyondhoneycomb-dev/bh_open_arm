"""Head-of-line (HOL) blocking characterisation report for the single WebSocket path.

`16` D-2 revision H2 establishes that HOL blocking on a single WebSocket is
*structural*, not incidental: RFC 6455 delivers messages in order and does not
interleave frames of concurrent messages, and the stack applies no receive-side
backpressure, so a large or slow message at the head delays everything behind it.
`WP-0B-06` records this as the HOL characteristic report.

The report has two parts kept deliberately separate. The *structural* part is the
always-true cause (the two RFC/stack facts above); it needs no hardware and is
stated here. The *measured* part is the observed head-of-line delay distribution
under real traffic, which needs a running dashboard socket and is therefore
deferred — represented honestly as an absent distribution until samples arrive,
never as a fabricated zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from ops.hw.usb.distribution import Distribution, compute_distribution

# The two structural causes `16` D-2 H2 names; both are properties of the protocol
# and stack, so they hold regardless of measurement.
RFC6455_NON_INTERLEAVED = (
    "RFC 6455 delivers messages in order and does not interleave frames of "
    "concurrent messages, so a head message blocks those queued behind it"
)
NO_RECEIVE_BACKPRESSURE = (
    "the WebSocket stack applies no receive-side backpressure, so a slow consumer "
    "lets the send queue grow rather than throttling the producer"
)


@dataclass(frozen=True)
class HolReport:
    """The HOL characteristic report: structural cause plus measured delay, if any.

    Attributes:
        hol_inevitable: Always True — the two structural causes make it so; recorded
            as a field so the artifact states the verdict, not just the reasons.
        causes: The structural reasons HOL is inevitable on a single socket.
        delay_distribution: Observed head-of-line delay distribution, or None when
            no real traffic has been measured yet (the deferred case).
    """

    hol_inevitable: bool
    causes: tuple[str, ...]
    delay_distribution: Distribution | None

    def as_dict(self) -> dict[str, object]:
        """Project to a JSON-serialisable mapping for the artifact.

        Returns:
            (dict[str, object]) The report as plain data; a None distribution is
            rendered as null so a reader can tell "unmeasured" from "measured zero".
        """
        return {
            "hol_inevitable": self.hol_inevitable,
            "causes": list(self.causes),
            "delay_distribution": (
                self.delay_distribution.as_dict() if self.delay_distribution is not None else None
            ),
        }


def build_hol_report(head_of_line_delay_us: list[float] | None = None) -> HolReport:
    """Build the HOL report, attaching a measured delay distribution when supplied.

    Args:
        head_of_line_delay_us: Observed per-message head-of-line delays in
            microseconds, or None when unmeasured (the deferred, hardware-pending
            case). An empty list is treated as unmeasured, since an empty
            distribution would read as a measured result of nothing.

    Returns:
        (HolReport) The report; `hol_inevitable` is always True on the single socket.
    """
    distribution = (
        compute_distribution(head_of_line_delay_us, unit="us") if head_of_line_delay_us else None
    )
    return HolReport(
        hol_inevitable=True,
        causes=(RFC6455_NON_INTERLEAVED, NO_RECEIVE_BACKPRESSURE),
        delay_distribution=distribution,
    )
