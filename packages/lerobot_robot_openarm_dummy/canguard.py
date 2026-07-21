"""A runtime guard proving the dummy opens no CAN socket (acceptance ③).

The static checker rejects CAN symbols in the source; this is the dynamic half. It
replaces `socket.socket` for the duration of a `with` block and raises the instant
anything asks for the `AF_CAN` address family — a SocketCAN socket is exactly how a
follower would reach the bus, and `09` FR-SIM-098 forbids the SIM path from opening
it. Running the whole dummy lifecycle inside the guard and observing zero `AF_CAN`
attempts is the runtime proof.

The guard is intentionally narrow: it forbids only the CAN family, so a dummy that
legitimately used a TCP socket (it does not) would be unaffected. It counts
attempts so a test can assert the count is zero, and it re-raises so a mistaken CAN
open fails loudly rather than silently succeeding.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

# The SocketCAN address family. Absent on non-Linux platforms, so it is resolved
# defensively; where it does not exist, no CAN socket can be opened anyway.
_AF_CAN = getattr(socket, "AF_CAN", None)


class CanSocketOpenedError(AssertionError):
    """Raised when code under the guard tries to open a CAN-family socket."""


@dataclass
class CanGuardReport:
    """The outcome of a guarded block.

    Attributes:
        can_socket_attempts: How many times an `AF_CAN` socket was requested. Zero is
            the acceptance ③ condition; the guard also raises on the first attempt,
            so a non-zero count only ever appears if raising is suppressed upstream.
    """

    can_socket_attempts: int = 0


@contextmanager
def forbid_can_sockets() -> Iterator[CanGuardReport]:
    """Forbid CAN-family socket creation for the duration of the block.

    Yields:
        (CanGuardReport) A live report; read `can_socket_attempts` after the block.

    Raises:
        CanSocketOpenedError: The moment guarded code requests an `AF_CAN` socket.
    """
    report = CanGuardReport()
    real_socket = socket.socket

    class _GuardedSocket(real_socket):  # type: ignore[valid-type, misc]
        """A socket subclass that refuses the CAN address family."""

        def __init__(self, family: int = socket.AF_INET, *args: object, **kwargs: object) -> None:
            if _AF_CAN is not None and family == _AF_CAN:
                report.can_socket_attempts += 1
                raise CanSocketOpenedError(
                    "code under forbid_can_sockets tried to open an AF_CAN socket "
                    "(09 FR-SIM-098: the SIM path must not open the bus)"
                )
            super().__init__(family, *args, **kwargs)

    socket.socket = _GuardedSocket  # type: ignore[misc]
    try:
        yield report
    finally:
        socket.socket = real_socket  # type: ignore[misc]
