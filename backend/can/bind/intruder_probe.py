"""Adapter: WP-0B-03 TX-intruder faults as a non-cooperating-binder `BindProbe`.

The flock probe (`LockBindProbe`) sees only a *cooperating* second binder. The one
that matters most here — a second *writer* that opened its own socket without
taking our lock (`01` FR-SYS-010's `openarm_driver`, `12` §2.9's second socket) —
is invisible to the flock, and is exactly what WP-0B-03's `TxCounterWatchdog`
catches: unaccounted TX frames on the link mean a writer the backend never spoke
for. This adapter turns each such `TxMismatchFault` into a `ForeignBinder`, so the
one gate that refuses on a flock holder also refuses on a live TX intruder.

The WARN/FAULT split WP-0B-03 fixes is preserved: only FAULT-class signals (a
second writer) become binders. A `ListenerWarning` is a passive reader that under
kernel fan-out steals nothing (`01` FR-SYS-007 revised); it is advisory and must
not gate a health report, so it is deliberately not mapped — which is enforced
structurally here by accepting only faults.

Live TX-counter reads need a real interface (vcan/hardware), so feeding this probe
from a running `TxCounterWatchdog` is deferred; the fault→binder mapping is pure
and is verified here against synthetic faults, and re-run against real captures by
`reverify`.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.can.bind.double_bind import ForeignBinder
from backend.can.intruder.signals import TxMismatchFault

# Probe-source label for a binder found by WP-0B-03's TX-counter watchdog.
SOURCE_TX_WATCHDOG = "tx-watchdog"


class IntruderBindProbe:
    """Report WP-0B-03 TX-intruder faults as foreign binders (non-cooperating writers).

    Each `TxMismatchFault` is a second writer — the double bind the cooperative
    flock cannot see — so it is reported as a `ForeignBinder`, with the PID left
    unknown because the TX watchdog identifies frames on the link, not a process.

    Args:
        faults: TX-mismatch faults evaluated by WP-0B-03's `TxCounterWatchdog` on
            a live interface, or replayed from a real capture.
    """

    def __init__(self, faults: Sequence[TxMismatchFault]) -> None:
        self.faults = tuple(faults)

    def foreign_binders(self, ifaces: Sequence[str]) -> tuple[ForeignBinder, ...]:
        """Map each TX fault on a probed interface to a foreign-binder record.

        Args:
            ifaces: Interfaces to report on.

        Returns:
            (tuple[ForeignBinder, ...]) One binder per TX fault whose interface is
            among those asked about.
        """
        wanted = set(ifaces)
        return tuple(
            ForeignBinder(
                iface=fault.iface,
                source=SOURCE_TX_WATCHDOG,
                detail=(
                    f"unaccounted TX frames on {fault.iface}: observed {fault.observed_tx} "
                    f"vs expected {fault.expected_tx} (+{fault.excess}) — second writer"
                ),
                holder_pid=None,
            )
            for fault in self.faults
            if fault.iface in wanted
        )
