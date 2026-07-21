"""The all-or-nothing CAN lock manager: acquire every channel, or hold none.

`01` FR-SYS-005 / `02` FR-CON-010 require the application to hold an exclusive
`flock(LOCK_EX|LOCK_NB)` on every CAN channel *before* `Robot.connect()`, and to
refuse startup — naming the holder — on any failure. The invariant this manager
enforces is that there is no partial state: acquiring four channels means all four
or none. A run that gets three and is refused the fourth releases the three it took
before it returns, so a refused startup never leaves a channel locked (acceptance ②).

Ownership and lifecycle: the manager owns the open file descriptors of the locks it
holds. They stay open for the life of the hold — closing an fd releases its flock —
so `release_all` (or process death, which the kernel handles) is the only way a lock
lets go. One manager instance owns one process's locks; it is not shared across
threads without external synchronisation.

This module imports no CAN stack. The lock is filesystem state (VFS `flock`), wholly
independent of any socket, which is exactly why it can be taken before the socket
exists.
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass

from backend.can.lock.holder import (
    LockHolderReport,
    read_holder_record,
    write_holder_record,
)
from backend.can.lock.paths import CANONICAL_LOCK_DIR, normalize_lock_path

_OPEN_FLAGS = os.O_RDWR | os.O_CREAT
_OPEN_MODE = 0o644


@dataclass(frozen=True)
class AcquireResult:
    """Outcome of an all-or-nothing acquisition attempt.

    Attributes:
        ok: True when every requested channel was acquired and is now held.
        held: Interfaces held after the call — every request on success, empty on
            failure (the partial acquisitions were released).
        blocked_iface: The interface whose lock was refused, on failure.
        holder: The holder of `blocked_iface`, on failure.
    """

    ok: bool
    held: tuple[str, ...]
    blocked_iface: str | None
    holder: LockHolderReport | None


@dataclass(frozen=True)
class LockState:
    """Runtime lock state for one interface (`01` FR-SYS-009 query source).

    Attributes:
        iface: The interface.
        lock_path: Absolute path of its lock file.
        held_by_self: True when *this* manager holds the lock.
        holder: The current holder when another process holds it, else None.
    """

    iface: str
    lock_path: str
    held_by_self: bool
    holder: LockHolderReport | None


class LockManager:
    """Holds an all-or-nothing set of CAN channel locks for one process.

    Args:
        lock_dir: Directory the lock files live in. Defaults to the canonical
            `/run/lock`; tests and non-writable hosts override it.
    """

    def __init__(self, lock_dir: str = CANONICAL_LOCK_DIR) -> None:
        self.lock_dir = lock_dir
        # Interface -> open, flocked file descriptor. Membership *is* the set of
        # locks this manager holds; the fd stays open for the life of the hold.
        self._held: dict[str, int] = {}

    def held_ifaces(self) -> tuple[str, ...]:
        """Return the interfaces this manager currently holds, in sorted order.

        Returns:
            (tuple[str, ...]) Held interface names.
        """
        return tuple(sorted(self._held))

    def is_held(self, iface: str) -> bool:
        """Report whether this manager holds the lock for an interface.

        Args:
            iface: Interface to check.

        Returns:
            (bool) True when this manager holds it.
        """
        return iface in self._held

    def all_held(self, ifaces: Sequence[str]) -> bool:
        """Report whether every named interface is held by this manager.

        This is the precondition the connect guard (acceptance ④) and the
        measurement WPs (`WP-0B-06`/`WP-0B-07`, "lock-not-held measurement is
        invalid") check before proceeding.

        Args:
            ifaces: Interfaces that must all be held.

        Returns:
            (bool) True when the held set covers every named interface.
        """
        return all(iface in self._held for iface in ifaces)

    def acquire_all(self, ifaces: Sequence[str]) -> AcquireResult:
        """Acquire the lock for every interface, or acquire none.

        Interfaces are taken in the given order. The first refusal releases every
        lock already taken in this call and returns a failure naming the holder of
        the refused channel, so the manager never ends a call in a partial state.

        Idempotent per interface: an interface this manager already holds is not
        re-locked (flock on a second fd for the same file, held by the same process,
        would otherwise self-deadlock under `LOCK_NB`).

        Args:
            ifaces: Interfaces to lock.

        Returns:
            (AcquireResult) Success with the full held set, or failure with the
            blocked interface and its holder and an unchanged prior held set.
        """
        acquired_now: list[str] = []
        for iface in ifaces:
            if iface in self._held:
                continue
            holder = self._try_acquire(iface)
            if holder is not None:
                for taken in acquired_now:
                    self._release(taken)
                return AcquireResult(ok=False, held=(), blocked_iface=iface, holder=holder)
            acquired_now.append(iface)
        return AcquireResult(ok=True, held=self.held_ifaces(), blocked_iface=None, holder=None)

    def release_all(self) -> None:
        """Release every lock this manager holds.

        Safe to call when nothing is held. After it returns, `held_ifaces` is empty.
        """
        for iface in list(self._held):
            self._release(iface)

    def lock_state(self, ifaces: Sequence[str]) -> tuple[LockState, ...]:
        """Return the runtime lock state for a set of interfaces.

        This is the data source for the `01` FR-SYS-009 REST + WS query. For an
        interface this manager holds, the state is reported from our own record; for
        one we do not hold, it is probed non-blockingly — a momentary `LOCK_NB`
        acquire that is immediately released tells whether another process holds it,
        and the holder record names who.

        Args:
            ifaces: Interfaces to report on.

        Returns:
            (tuple[LockState, ...]) One state per interface, in input order.
        """
        states: list[LockState] = []
        for iface in ifaces:
            path = normalize_lock_path(iface, self.lock_dir)
            if iface in self._held:
                states.append(
                    LockState(
                        iface=iface,
                        lock_path=str(path),
                        held_by_self=True,
                        holder=None,
                    )
                )
                continue
            states.append(
                LockState(
                    iface=iface,
                    lock_path=str(path),
                    held_by_self=False,
                    holder=self._probe_holder(iface),
                )
            )
        return tuple(states)

    def _try_acquire(self, iface: str) -> LockHolderReport | None:
        """Attempt to acquire one interface's lock.

        Args:
            iface: Interface to lock.

        Returns:
            (LockHolderReport | None) None on success (the fd is now held), or the
            current holder's report on refusal (the fd is closed before returning).
        """
        path = normalize_lock_path(iface, self.lock_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, _OPEN_FLAGS, _OPEN_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            report = read_holder_record(fd, iface, path)
            os.close(fd)
            return report
        write_holder_record(fd, iface, path, time.time())
        self._held[iface] = fd
        return None

    def _release(self, iface: str) -> None:
        """Release one interface's lock and forget it.

        Args:
            iface: Interface to release. A no-op when not held.
        """
        fd = self._held.pop(iface, None)
        if fd is None:
            return
        # Truncate before unlocking so a subsequent acquirer never reads a departed
        # holder's identity; closing the fd is what finally drops the flock.
        os.ftruncate(fd, 0)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def _probe_holder(self, iface: str) -> LockHolderReport | None:
        """Non-blockingly report who holds an interface's lock, if anyone.

        Args:
            iface: Interface to probe.

        Returns:
            (LockHolderReport | None) The holder, or None when the lock is free.
        """
        path = normalize_lock_path(iface, self.lock_dir)
        if not path.exists():
            return None
        fd = os.open(path, _OPEN_FLAGS, _OPEN_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            report = read_holder_record(fd, iface, path)
            os.close(fd)
            return report
        # We got it, so no one else holds it — let go without disturbing anything.
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        return None
