"""The two intruder signals, kept type-distinct so they can never be merged.

`01` FR-SYS-007 (revised) splits CAN-bus intrusion into two threats that a single
alarm would conflate, and the WP contract is explicit that they stay apart:

- An *extra RX listener* is a passive reader (a manual ``candump``, a monitor). Under
  the kernel's fan-out model a passive reader is copied every matching frame but
  injects nothing, so it steals no response. It is a WARN — the user may knowingly
  have one open and proceed.
- An *unaccounted TX frame* is a second writer injecting commands the backend never
  sent. That is the real hazard (`01` FR-SYS-007), so it is a FAULT with no
  auto-recovery, and it is invisible to the listener check because a writer can
  register no receive filter at all.

Two frozen dataclasses rather than one type with a severity argument: a caller
cannot construct a listener finding at FAULT severity or a TX finding at WARN
severity, because severity is a property fixed per type. Merging the two signals
would require changing a type — which a reviewer sees — not passing a different enum
value, which they might not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IntruderSeverity(Enum):
    """Severity of an intruder signal. The two values never share a carrier type.

    WARN is advisory: the user may acknowledge it and proceed. FAULT is terminal:
    there is no auto-recovery, and only an explicit operator acknowledgement clears
    it (`IntruderMonitor.manual_clear`).
    """

    WARN = "WARN"
    FAULT = "FAULT"


@dataclass(frozen=True)
class ListenerWarning:
    """An RX-listener excess: more receivers on the bus than this process opened.

    Emitted by the RX-listener check (threat (a)). Never blocks — under fan-out the
    extra listener steals nothing — so its severity is fixed WARN and cannot be
    constructed as a FAULT.

    Attributes:
        iface: Interface the excess was observed on.
        observed_listeners: Total receive-all registrations seen for the interface.
        expected_listeners: Registrations this process legitimately owns.
    """

    iface: str
    observed_listeners: int
    expected_listeners: int

    @property
    def severity(self) -> IntruderSeverity:
        """Return the fixed severity of this signal (always WARN)."""
        return IntruderSeverity.WARN

    @property
    def excess(self) -> int:
        """Return how many listeners exceed this process's own registrations."""
        return self.observed_listeners - self.expected_listeners


@dataclass(frozen=True)
class TxMismatchFault:
    """A TX-counter mismatch: frames left the interface that the backend never sent.

    Emitted by the TX-counter watchdog (threat (b)). A second writer is the only way
    the link TX delta can disagree with the backend's own sent-frame count, so its
    severity is fixed FAULT and cannot be constructed as a WARN. No auto-recovery.

    Attributes:
        iface: Interface the mismatch was observed on.
        observed_tx: Link TX packet counter read from ``ip -s link show``.
        expected_tx: Counter value the backend's own sent-frame count predicts.
    """

    iface: str
    observed_tx: int
    expected_tx: int

    @property
    def severity(self) -> IntruderSeverity:
        """Return the fixed severity of this signal (always FAULT)."""
        return IntruderSeverity.FAULT

    @property
    def excess(self) -> int:
        """Return the unaccounted TX frames (observed minus predicted)."""
        return self.observed_tx - self.expected_tx
