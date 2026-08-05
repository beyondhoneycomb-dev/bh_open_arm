"""One connected client: its role, its session id, and its preview sink (`WP-3B-15`).

The session is what the dispatcher decides against, and it deliberately holds no lease,
no latch and no generation. Those belong to `backend.deadman` and `backend.actuation`,
which are shared across every connection — a per-connection copy of any of them would be
a second lease or a second latch, and two clients would then disagree about whether the
arm is held.

The role is read at the handshake and never re-negotiated on a live socket. A client that
wants a different role opens a new connection, so `authorize_send` judges a role that
cannot have changed between the check and the act.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ws.sink import WebSocketPreviewSink
from contracts.ws import WsRole


@dataclass(frozen=True)
class WsSession:
    """One client's connection identity and its outbound preview surface.

    Attributes:
        role: The `CTR-WS@v2` role this connection holds. Frozen for the connection's
            lifetime; `authorize_send` reads it on every inbound frame.
        session_id: The client's session identifier, carried on lease and stop frames
            for attribution. It identifies who acted; it decides nothing.
        preview_sink: This connection's TX-only binary surface. Held here because it is
            per-connection state with the same lifetime as the socket, unlike the lease
            and the latch, which are the arm's and are shared.
    """

    role: WsRole
    session_id: str
    preview_sink: WebSocketPreviewSink


__all__ = ["WsSession"]
