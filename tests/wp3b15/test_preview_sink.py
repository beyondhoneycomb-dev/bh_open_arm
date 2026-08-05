"""The `PreviewSink` over a real socket: queue in, bytes out, backlog measured.

Two levels, because they prove different things. The unit tests drive the sink directly
against a recording sender, so the queue/drain/backlog behaviour is checked without a
socket in the way. The end-to-end test then puts the *same* class on a live connection
and reads the bytes off the client, which is the only way to show that what satisfies the
`PreviewSink` Protocol also satisfies a WebSocket.

The sink is reached end to end through `WsSession.preview_sink` from inside the command
sink, because that is where a host would reach it too — a per-connection TX surface is
handed out with the session. No test-only hook exists to grab it.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.sensing.preview.sink import PreviewSink
from backend.ws import WebSocketPreviewSink, WsSession
from contracts.ws import (
    BUFFERED_AMOUNT_THRESHOLD_BYTES,
    WsFrameType,
    WsRole,
    should_drop_under_backpressure,
)
from tests.wp3b15.conftest import WsFixture, connect, frame

PREVIEW_PAYLOAD = b"left_wrist:rgb\x00packed-preview"


class RecordingSender:
    """A `BinarySender` that keeps what it was asked to send, in order."""

    def __init__(self) -> None:
        """Create a sender that has sent nothing."""
        self.sent: list[bytes] = []

    async def send_bytes(self, data: bytes) -> None:
        """Record one binary frame."""
        self.sent.append(data)


def test_the_sink_satisfies_the_preview_protocol() -> None:
    """It is the `PreviewSink` `WP-3B-06` declared, checked structurally not by claim."""

    async def build() -> WebSocketPreviewSink:
        return WebSocketPreviewSink(RecordingSender())

    assert isinstance(asyncio.run(build()), PreviewSink)


def test_queued_bytes_are_sent_oldest_first_and_the_backlog_returns_to_zero() -> None:
    """One drain empties the queue in order, and the reported backlog follows it down."""

    async def exercise() -> tuple[list[bytes], list[bytes], int, int]:
        sender = RecordingSender()
        sink = WebSocketPreviewSink(sender)
        sink.send_binary(b"first")
        sink.send_binary(b"second")
        queued = sink.buffered_amount()
        drained = await sink.drain_once()
        return drained, sender.sent, queued, sink.buffered_amount()

    drained, sent, queued, remaining = asyncio.run(exercise())
    assert drained == [b"first", b"second"]
    assert sent == [b"first", b"second"]
    assert queued == len(b"first") + len(b"second")
    assert remaining == 0


def test_send_binary_does_not_wait_for_the_drain() -> None:
    """The capture-side caller is never blocked: queueing completes with nothing draining.

    A sink that awaited the socket here would let a busy link back-pressure the camera
    loop, which is the one thing `WP-3B-06` forbids of a preview.
    """

    async def exercise() -> int:
        sink = WebSocketPreviewSink(RecordingSender())
        for _ in range(100):
            sink.send_binary(PREVIEW_PAYLOAD)
        return sink.buffered_amount()

    assert asyncio.run(exercise()) == 100 * len(PREVIEW_PAYLOAD)


def test_the_reported_backlog_is_what_the_backpressure_rule_reads() -> None:
    """Past the `CTR-WS@v2` threshold the shared rule sheds camera frames on this number."""

    async def exercise() -> tuple[bool, bool]:
        sink = WebSocketPreviewSink(RecordingSender())
        idle = should_drop_under_backpressure(WsFrameType.CAMERA, sink.buffered_amount())
        sink.send_binary(b"\x00" * (BUFFERED_AMOUNT_THRESHOLD_BYTES + 1))
        return idle, should_drop_under_backpressure(WsFrameType.CAMERA, sink.buffered_amount())

    idle, saturated = asyncio.run(exercise())
    assert idle is False
    assert saturated is True


def test_the_sink_on_a_live_connection_sends_on_the_real_socket(ws: WsFixture) -> None:
    """The session's sink transmits over the connection it belongs to.

    The session is obtained the way a host obtains one — from the command sink, which is
    handed the `WsSession` and through it the per-connection TX surface. There is no
    test-only accessor, so what this exercises is the wiring a deployment would use.
    """
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(frame(WsFrameType.COMMAND))
        # The reply-less command has been handled by the time the next send is queued
        # behind it, so the session is recorded before the sink is reached for.
        socket.send_json(frame(WsFrameType.COMMAND))
        session: WsSession = ws.sessions[0]
        session.preview_sink.send_binary(PREVIEW_PAYLOAD)
        received = socket.receive_bytes()

    assert received == PREVIEW_PAYLOAD


def test_a_sink_built_off_the_loop_is_refused() -> None:
    """Construction captures the socket's loop, so building one without a loop fails loudly.

    A sink that silently tolerated this would defer the failure to the first
    `send_binary` from a producer thread, where it would surface as a preview that never
    arrives rather than as a wiring error.
    """
    with pytest.raises(RuntimeError):
        WebSocketPreviewSink(RecordingSender())
