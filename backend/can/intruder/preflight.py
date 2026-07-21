"""Preflight occupancy check (`02` FR-CON-011): is the bus already taken before we bind?

`01` FR-SYS-007 (revised) resolves the reader/writer asymmetry: only a *writer* needs
exclusion, because passive readers fan-out-share the bus harmlessly. This preflight
encodes that split into two questions asked before ``Robot.connect()``:

- **Writer occupancy** — is another process already holding the cooperative writer
  lock for this interface? That is a hard occupancy: two writers is the exact hazard
  the lock exists to prevent, so it blocks (``may_proceed`` is false). The answer
  comes from the WP-0B-01 `LockManager`'s non-blocking `lock_state` probe, which
  names the holder without disturbing it.
- **Reader occupancy** — are there listeners on the bus beyond our own? That is soft:
  a monitoring ``candump`` is fine, so it is surfaced as a WARN and does not block.

This module imports the lock manager as a foundation (WP-0B-01) and opens no socket
of its own; the probe is filesystem state plus captured proc text.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.can.intruder.listener import RxListenerCheck
from backend.can.intruder.signals import ListenerWarning
from backend.can.lock import LockHolderReport, LockManager


@dataclass(frozen=True)
class PreflightReport:
    """Outcome of the preflight occupancy check for one interface.

    Attributes:
        iface: Interface that was checked.
        writer_occupied: True when another process holds the writer lock.
        writer_holder: The foreign writer's holder report, when occupied.
        listener_warning: A WARN when extra listeners are on the bus, else None.
    """

    iface: str
    writer_occupied: bool
    writer_holder: LockHolderReport | None
    listener_warning: ListenerWarning | None

    @property
    def may_proceed(self) -> bool:
        """Report whether connect may proceed: blocked only by a foreign writer.

        A listener warning alone never blocks — it is advisory, mirroring the
        monitor's WARN/FAULT split.
        """
        return not self.writer_occupied


class PreflightCheck:
    """Ask whether an interface is already occupied before we bind to it.

    Args:
        iface: Interface to check.
        lock_manager: The WP-0B-01 lock manager whose non-blocking probe answers
            writer occupancy. Injected so a test can point it at a temp lock dir.
        listener_check: The RX-listener check that answers reader occupancy.
    """

    def __init__(
        self, iface: str, lock_manager: LockManager, listener_check: RxListenerCheck
    ) -> None:
        self.iface = iface
        self.lock_manager = lock_manager
        self.listener_check = listener_check

    def run(self, rcvlist_text: str) -> PreflightReport:
        """Probe writer and reader occupancy and report whether connect may proceed.

        The writer probe is non-blocking and side-effect-free: it never takes the
        lock, only reports whether someone else holds it, so running the preflight
        does not itself become the occupant.

        Args:
            rcvlist_text: Captured ``/proc/net/can/rcvlist_all`` contents.

        Returns:
            (PreflightReport) Writer occupancy, its holder, and any listener warning.
        """
        state = self.lock_manager.lock_state([self.iface])[0]
        writer_occupied = state.holder is not None and not state.held_by_self
        warning = self.listener_check.evaluate_rcvlist(rcvlist_text)
        return PreflightReport(
            iface=self.iface,
            writer_occupied=writer_occupied,
            writer_holder=state.holder,
            listener_warning=warning,
        )
