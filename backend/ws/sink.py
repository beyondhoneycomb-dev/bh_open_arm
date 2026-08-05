"""The `PreviewSink` over a real WebSocket — the first concrete one (`WP-3B-15`).

`backend/sensing/preview/sink.py` declares the two-method TX surface a preview frame
leaves through, and until now nothing outside a test satisfied it. This is that
implementation, and the whole of what it adds is a queue, because the two sides do not
agree on colour: `PreviewPipe.run_once` calls `send_binary` synchronously
(`backend/sensing/preview/pipe.py:163`), while an ASGI WebSocket send is a coroutine.
Queue in, drain out, and the pipe never learns the difference.

What `buffered_amount()` actually measures, stated plainly because the name promises
more than ASGI can deliver: it is the bytes **this sink** has accepted and not yet
handed to the transport. The browser's `bufferedAmount` also counts what the kernel
socket buffer still holds, and ASGI exposes no such number — there is no flush callback
and no send-buffer query anywhere in the interface. So this is a lower bound on the real
backlog, never an over-estimate. The direction of the error is the safe one for the
`CTR-WS@v2` backpressure rule: under-reporting sheds camera frames later than a perfect
measure would, never earlier, so a dead-man renewal is never starved by this sink
dropping the wrong class. It does mean a link that is congested purely below this
process looks idle from here, and only a transport that reports its own buffer level
closes that gap.

Ownership / threading: one sink per connection, holding that connection's socket. The
producer side (`send_binary`, `buffered_amount`) is safe to call from any thread — the
capture-side pipe is not required to run on the event loop — so the queue is a plain
deque under a lock and the wake-up crosses to the loop through `call_soon_threadsafe`.
The consumer side (`drain_forever`) must run on the loop that owns the socket, and the
connection handler is what starts and cancels it.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Protocol


class BinarySender(Protocol):
    """The one call this sink makes into the socket it was handed.

    Narrower than `starlette.websockets.WebSocket` on purpose: a sink that could reach
    a receive method would be a preview surface with an inbound path, which is exactly
    what `PreviewSink` exists to make unconstructible (`02b` §6.2). Starlette's
    `WebSocket` satisfies this structurally.
    """

    async def send_bytes(self, data: bytes) -> None:
        """Send one binary frame on the socket."""
        ...


class WebSocketPreviewSink:
    """The single-WebSocket TX surface for preview frames, over a real socket.

    Ownership: holds the connection's socket (not owned — the connection handler owns
    it), the outbound byte queue, and the loop the socket belongs to. It holds no camera
    and no source; frames arrive through `send_binary` and leave through the socket.
    """

    def __init__(self, websocket: BinarySender) -> None:
        """Bind the sink to one connection's socket.

        Must be constructed on the event loop that owns the socket: the loop is captured
        here so a producer thread can wake the drain without holding a loop reference of
        its own.

        Args:
            websocket: The connection's binary send surface.

        Raises:
            RuntimeError: If constructed outside a running event loop.
        """
        self._websocket = websocket
        self._loop = asyncio.get_running_loop()
        self._pending: deque[bytes] = deque()
        self._pending_bytes = 0
        self._lock = threading.Lock()
        self._wake = asyncio.Event()

    def buffered_amount(self) -> int:
        """Bytes accepted by this sink and not yet handed to the transport.

        Returns:
            (int) The queued byte count — a lower bound on the link's real backlog, for
            the reason the module docstring gives.
        """
        with self._lock:
            return self._pending_bytes

    def send_binary(self, data: bytes) -> None:
        """Queue one preview frame for transmission; never blocks the caller.

        Non-blocking is the contract, not a convenience: the caller is the capture-side
        preview pipe, and a sink that blocked it would make a busy link back-pressure the
        camera loop — the one thing `WP-3B-06` forbids.

        Args:
            data: The packed preview frame.
        """
        with self._lock:
            self._pending.append(data)
            self._pending_bytes += len(data)
        self._loop.call_soon_threadsafe(self._wake.set)

    async def drain_once(self) -> list[bytes]:
        """Wait for queued frames and send every one of them, oldest first.

        Returns:
            (list[bytes]) The frames sent, in send order. Never empty — the call waits
            until there is something to send.
        """
        await self._wake.wait()
        sent: list[bytes] = []
        while True:
            with self._lock:
                if not self._pending:
                    self._wake.clear()
                    break
                data = self._pending.popleft()
                self._pending_bytes -= len(data)
            await self._websocket.send_bytes(data)
            sent.append(data)
        return sent

    async def drain_forever(self) -> None:
        """Send queued frames until the task is cancelled.

        The connection handler runs this as its own task and cancels it on disconnect;
        the cancellation propagates out of the `await`, so there is no stop flag to get
        wrong and no frame is half-sent.
        """
        while True:
            await self.drain_once()


__all__ = ["BinarySender", "WebSocketPreviewSink"]
