"""Intruder injection harness for the live-vcan acceptance (①, ②, ④ — deferred).

These injectors bind real ``AF_CAN`` sockets, so they run only against a real vcan
and are exercised by tests that skip with a reason on a host without one. They are
built and correct now so that the moment a vcan exists the deferred acceptance runs
unchanged.

Raw sockets rather than python-can, because acceptance ④ needs a writer that
registers *no* receive filter — a TX intruder invisible to the RX-listener check.
That requires setting ``CAN_RAW_FILTER`` to an empty filter set, which is exactly the
control a raw socket gives:

- `PassiveReaderInjector` — the manual ``candump`` of acceptance ①: a default-filtered
  socket that appears in ``rcvlist_all`` and sends nothing.
- `ActiveWriterInjector` — the general second writer of acceptance ②: a default-filtered
  socket that both listens and sends, so it trips *both* checks.
- `WriteOnlyInjector` — the acceptance ④ threat: a zero-filter socket that sends but
  registers no listener, so it trips the TX watchdog while the RX check stays blind.
"""

from __future__ import annotations

import socket
import struct
from types import TracebackType

# SocketCAN frame layout: can_id (u32, native), can_dlc (u8), 3 pad bytes, 8 data
# bytes — 16 bytes total (linux/can.h struct can_frame).
_CAN_FRAME = struct.Struct("=IB3x8s")
_MAX_DLC = 8
# An empty CAN_RAW_FILTER set: the socket registers no receiver, so it never appears
# in /proc/net/can/rcvlist_all yet may still transmit.
_EMPTY_FILTER = b""


def _open_can_socket(iface: str, receive: bool) -> socket.socket:
    """Open and bind a raw CAN socket, optionally with no receive filter.

    Args:
        iface: CAN interface to bind to.
        receive: When False, install an empty ``CAN_RAW_FILTER`` so the socket
            registers no listener (a write-only intruder).

    Returns:
        (socket.socket) The bound socket; the caller owns and must close it.
    """
    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    if not receive:
        sock.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, _EMPTY_FILTER)
    sock.bind((iface,))
    return sock


def _send_frames(sock: socket.socket, count: int) -> None:
    """Transmit ``count`` filler CAN frames on a bound socket."""
    frame = _CAN_FRAME.pack(0x123, _MAX_DLC, bytes(_MAX_DLC))
    for _ in range(count):
        sock.send(frame)


class _BoundInjector:
    """Base for injectors that hold one bound CAN socket for a context's lifetime.

    Args:
        iface: CAN interface to bind to.
        receive: Whether the socket registers a receive filter.
    """

    def __init__(self, iface: str, receive: bool) -> None:
        self.iface = iface
        self._receive = receive
        self._sock: socket.socket | None = None

    def __enter__(self) -> _BoundInjector:
        self._sock = _open_can_socket(self.iface, self._receive)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _require_socket(self) -> socket.socket:
        """Return the bound socket, or raise if used outside the context."""
        if self._sock is None:
            raise RuntimeError("injector used outside its context manager")
        return self._sock


class PassiveReaderInjector(_BoundInjector):
    """A passive reader (manual ``candump``): registers a listener, sends nothing.

    Args:
        iface: CAN interface to bind to.
    """

    def __init__(self, iface: str) -> None:
        super().__init__(iface, receive=True)


class ActiveWriterInjector(_BoundInjector):
    """A second writer that both listens and transmits, tripping both checks.

    Args:
        iface: CAN interface to bind to.
    """

    def __init__(self, iface: str) -> None:
        super().__init__(iface, receive=True)

    def inject(self, count: int) -> None:
        """Transmit ``count`` frames the backend never sent.

        Args:
            count: Number of intruder frames to send.
        """
        _send_frames(self._require_socket(), count)


class WriteOnlyInjector(_BoundInjector):
    """A TX-only intruder: transmits but registers no listener (acceptance ④).

    Args:
        iface: CAN interface to bind to.
    """

    def __init__(self, iface: str) -> None:
        super().__init__(iface, receive=False)

    def inject(self, count: int) -> None:
        """Transmit ``count`` frames while remaining invisible to the RX check.

        Args:
            count: Number of intruder frames to send.
        """
        _send_frames(self._require_socket(), count)
