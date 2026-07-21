"""The is_connected precondition: no "connected" report without the bind check.

`01` NFR-SYS-004 and this WP's contract state it as an ordering rule — the
double-bind-absence check is a *precondition* of reporting `is_connected=True`,
and a report that skips it is a silent success, which the spec counts as a
failure. `ConnectionGate` makes that ordering structural: the check runs first
and unconditionally, and the gate can return True only when the check found no
foreign binder *and* the transport reports up. No path through the gate returns
True without having asked "is anyone else bound?".

Threading/lifecycle: the gate holds a reference to the `DoubleBindCheck` and is
otherwise stateless; it is as reentrant as the probes behind the check.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from backend.can.bind.double_bind import DoubleBindCheck, ForeignBinder


class ConnectionGate:
    """Gate that reports connected only when no second bind exists and the link is up.

    Args:
        check: The double-bind check that must find nothing before a True report.
    """

    def __init__(self, check: DoubleBindCheck) -> None:
        self.check = check

    def is_connected(
        self,
        ifaces: Sequence[str],
        transport_connected: Callable[[], bool],
    ) -> bool:
        """Report connected only when no foreign binder exists and the transport is up.

        The bind check runs first and unconditionally. A detected foreign binder
        returns False *without* consulting `transport_connected` — the interface
        is contested, so normal operation may not be reported (NFR-SYS-004)
        whatever the transport would say. With no binder, the report is exactly
        the transport's own answer.

        Args:
            ifaces: Interfaces the connection uses; all are checked for a second bind.
            transport_connected: Zero-argument callable returning whether the
                underlying CAN transport is itself up. Called only once the bind
                check passes.

        Returns:
            (bool) True only when no foreign binder was found and the transport
            reports connected; False otherwise.
        """
        if self.check.foreign_binders(ifaces):
            return False
        return bool(transport_connected())

    def foreign_binders(self, ifaces: Sequence[str]) -> tuple[ForeignBinder, ...]:
        """Return the binders behind a False report, so the refusal is never silent.

        Args:
            ifaces: Interfaces to report on.

        Returns:
            (tuple[ForeignBinder, ...]) The foreign binders the check found.
        """
        return self.check.foreign_binders(ifaces)
