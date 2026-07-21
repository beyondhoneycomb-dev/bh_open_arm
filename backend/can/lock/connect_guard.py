"""The ordering gate: no CAN socket opens until every channel lock is held.

`01` FR-SYS-005 fixes the order — "acquire the lock of every channel *before*
`Robot.connect()`". This module is the runtime half of enforcing it (acceptance ④,
"a socket-open attempt without the lock is rejected at runtime"): the actual
socket-opening work is passed in as a callable, and the guard refuses to invoke it
unless the manager already holds every required channel. The static half lives in
`staticcheck.find_can_open_without_lock_import`.

`assert_lock_held` is the same precondition in bare form, exported for the
measurement WPs (`WP-0B-06`, `WP-0B-07`) whose specs declare that a measurement
taken without the lock held is invalid and must not be published.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from backend.can.lock.manager import LockManager

T = TypeVar("T")


class LockOrderingError(RuntimeError):
    """A CAN connection was attempted before its channel locks were held."""


def assert_lock_held(manager: LockManager, ifaces: Sequence[str]) -> None:
    """Raise unless the manager holds the lock for every named interface.

    Args:
        manager: The lock manager to check.
        ifaces: Interfaces that must all be held.

    Raises:
        LockOrderingError: If any named interface is not held.
    """
    missing = [iface for iface in ifaces if not manager.is_held(iface)]
    if missing:
        raise LockOrderingError(
            f"lock(s) not held for {missing}; acquire all channels before connect (01 FR-SYS-005)"
        )


def guarded_connect(
    manager: LockManager,
    ifaces: Sequence[str],
    open_connection: Callable[[], T],
) -> T:
    """Open a CAN connection only after every channel lock is held.

    The lock check strictly precedes the call to `open_connection`: on a missing
    lock the callable is never invoked, so no socket is ever opened out of order.

    Args:
        manager: Manager expected to hold the channel locks.
        ifaces: Interfaces the connection will use, all of which must be held.
        open_connection: Zero-argument callable that opens the socket(s) and
            returns whatever the caller's connect produces.

    Returns:
        (T) Whatever `open_connection` returns.

    Raises:
        LockOrderingError: If any channel lock is not held; `open_connection` is
            not called in that case.
    """
    assert_lock_held(manager, ifaces)
    return open_connection()
