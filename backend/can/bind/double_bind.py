"""Active double-bind detection: is a *second* process bound to our CAN interface?

`01` NFR-SYS-004 forbids any CAN client from reporting normal operation while
another process is bound to the same interface — "silent success is failure".
SocketCAN RAW has no exclusive bind (`16` §10.1) and the kernel loopback fans a
matching frame to *every* bound socket, so a second bind does not fail: it
succeeds silently and can then inject conflicting commands (`12` §2.9, second
socket = silent double bind). Detection therefore cannot wait for a bind error;
it must actively ask "who else is here?".

Two disjoint classes of second binder exist, and no single probe sees both:

- A *cooperating* binder — a process that honours our `flock` (`WP-0B-01`).
  `LockBindProbe` sees it: if we do not hold the exclusive lock, someone else
  does, and the holder record names them. This is VFS-level and runs anywhere.
- A *non-cooperating* binder — a rogue `candump` or a second python-can writer
  that opened its own socket without taking our lock. Only a live SocketCAN read
  (RX-listener count / TX-counter watchdog, `WP-0B-03`) sees it, and that needs a
  real interface. It plugs in here as another `BindProbe`.

`openarm_driver` is the archetype of the non-cooperating binder (`01` FR-SYS-010:
it opens its own `openarm_can::CANSocket`); it cannot be caught at runtime by the
lock, which is exactly why its double bind is prevented statically, at import
time, by `staticcheck` — not detected here.

`DoubleBindCheck` unions whatever probes it is given, so one gate serves the
here-and-now flock probe and the deferred live SocketCAN probe identically.
This module opens no CAN socket; the flock probe it ships is filesystem state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.can.lock.manager import LockManager

# Probe-source labels, so a refusal names which detector saw the binder. `flock` is
# the cooperating-binder probe that runs here; the live labels are what the deferred
# SocketCAN probe (`WP-0B-03`) reports under.
SOURCE_FLOCK = "flock"
SOURCE_REPLAY = "replay"

# Sentinel ordinal for a binder whose PID is unknown (a live RX/TX probe may see a
# binder it cannot name); it sorts ahead of any real PID.
_UNKNOWN_PID_ORDER = -1


@dataclass(frozen=True)
class ForeignBinder:
    """A second process detected bound to (or holding the lock of) our interface.

    Attributes:
        iface: Interface the foreign binder was found on.
        source: Which probe found it (`SOURCE_FLOCK`, a live `WP-0B-03` label, …).
        detail: Human-readable evidence, for the refusal message.
        holder_pid: PID of the binder when known (the flock probe records it),
            else None — a live RX/TX probe may see a binder it cannot name.
    """

    iface: str
    source: str
    detail: str
    holder_pid: int | None


class BindProbe(Protocol):
    """One way of answering "is another process bound to these interfaces?".

    Implementations return the binders they can see and nothing else; the union
    across probes is the gate's concern, not any single probe's.
    """

    def foreign_binders(self, ifaces: Sequence[str]) -> tuple[ForeignBinder, ...]:
        """Return every foreign binder this probe sees on the given interfaces."""
        ...


class LockBindProbe:
    """Detect a *cooperating* second binder through the WP-0B-01 exclusive lock.

    A process that honours the cooperative `flock` and holds it *is* a second
    binder from our point of view: we cannot be the sole owner of an interface
    whose lock another process holds. This reads the manager's non-blocking lock
    state and reports every interface a foreign process holds. It opens no CAN
    socket, so — like the lock itself — it runs on any host.

    Args:
        manager: The WP-0B-01 lock manager whose held/foreign state is the signal.
    """

    def __init__(self, manager: LockManager) -> None:
        self.manager = manager

    def foreign_binders(self, ifaces: Sequence[str]) -> tuple[ForeignBinder, ...]:
        """Report every interface held by a process other than this manager.

        Args:
            ifaces: Interfaces to probe.

        Returns:
            (tuple[ForeignBinder, ...]) One binder per interface a foreign
            process holds; empty when we hold them all or they are free.
        """
        found: list[ForeignBinder] = []
        for state in self.manager.lock_state(ifaces):
            if state.held_by_self or state.holder is None:
                continue
            holder = state.holder
            found.append(
                ForeignBinder(
                    iface=state.iface,
                    source=SOURCE_FLOCK,
                    detail=f"lock held by pid {holder.holder_pid} ({holder.holder_cmdline})",
                    holder_pid=holder.holder_pid,
                )
            )
        return tuple(found)


class StaticBindProbe:
    """A probe reporting a fixed set of foreign binders — for replay and injection.

    Its purpose is to feed binders that were captured from a real rig (or the
    deferred `WP-0B-03` live probe) back through the very same gate the live
    probes feed (`reverify`), and to drive the gate deterministically under test.
    A binder is reported only for an interface actually asked about, so replaying
    a capture against a narrower interface set behaves like the live probes.

    Args:
        binders: The foreign binders this probe will report.
    """

    def __init__(self, binders: Sequence[ForeignBinder]) -> None:
        self.binders = tuple(binders)

    def foreign_binders(self, ifaces: Sequence[str]) -> tuple[ForeignBinder, ...]:
        """Return the held binders whose interface is among those asked about."""
        wanted = set(ifaces)
        return tuple(binder for binder in self.binders if binder.iface in wanted)


class DoubleBindError(RuntimeError):
    """A second process is bound to an interface we were about to report healthy."""


def _binder_order(binder: ForeignBinder) -> tuple[str, str, int, str]:
    """Total order for foreign binders, placing an unknown PID ahead of any real one.

    Args:
        binder: Binder to key.

    Returns:
        (tuple) Sort key over (iface, source, pid, detail).
    """
    pid = binder.holder_pid if binder.holder_pid is not None else _UNKNOWN_PID_ORDER
    return (binder.iface, binder.source, pid, binder.detail)


class DoubleBindCheck:
    """Union of bind probes; the precondition every "healthy" report must pass.

    The check has no opinion on how a binder was found — it unions the findings
    of its probes so the same object gates the flock probe that runs here and the
    live SocketCAN probe deferred to real hardware. A caller reports normal
    operation only when this check finds nothing (`ConnectionGate`).

    Args:
        probes: Probes whose findings are unioned. An empty sequence makes the
            check vacuous — a caller wiring only that would be reporting health
            with no evidence, which is the failure NFR-SYS-004 names, so at least
            one real probe must be supplied.
    """

    def __init__(self, probes: Sequence[BindProbe]) -> None:
        self.probes = tuple(probes)

    def foreign_binders(self, ifaces: Sequence[str]) -> tuple[ForeignBinder, ...]:
        """Return every foreign binder any probe sees, deduplicated and ordered.

        Args:
            ifaces: Interfaces to check.

        Returns:
            (tuple[ForeignBinder, ...]) The union across probes, sorted.
        """
        found: set[ForeignBinder] = set()
        for probe in self.probes:
            found.update(probe.foreign_binders(ifaces))
        return tuple(sorted(found, key=_binder_order))

    def assert_absent(self, ifaces: Sequence[str]) -> None:
        """Raise unless no probe sees a foreign binder on any named interface.

        The loud form of the precondition, for callers that treat a contested
        interface as a hard error rather than a False health report.

        Args:
            ifaces: Interfaces that must be free of any foreign binder.

        Raises:
            DoubleBindError: If any probe reports a binder, naming the evidence.
        """
        binders = self.foreign_binders(ifaces)
        if binders:
            details = [binder.detail for binder in binders]
            raise DoubleBindError(
                f"second bind present; refusing to report normal operation "
                f"(01 NFR-SYS-004): {details}"
            )
