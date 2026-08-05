"""The ASGI mount for the one realtime channel — no server, no module-level app.

`mount_realtime_channel` adds the websocket route to an application the caller already
has and binds nothing, which is what lets a test drive it in-process through
`TestClient` while a host serves the same object on a real port. The dependencies arrive
as arguments for the same reason `backend/config/api.py`'s `create_app` takes its store:
a host, a test and a deployment each supply their own, and importing this module resolves
no hardware and opens no socket.

The dependency the caller must get right, and the only one this module cannot check: the
`LatchTarget` passed here has to be the *same object* the `DeadmanController` was built
over. Two latches would mean a GUI stop that the deadman cannot see and a deadman expiry
the GUI cannot clear, which is the "second latch" this WP is forbidden to build. The
signature asks for both so a host wiring them apart has to do it visibly.

`CTR-WS@v2` D-2 permits exactly one realtime channel, so this function mounts exactly one
route. A second websocket route on the same app is a contract violation, and
`tests/wp3b15/test_single_channel.py` is what refuses it.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.actuation.clock import Clock
from backend.deadman import DeadmanController, LatchTarget
from backend.security.origin_policy import ControlChannelSecurity
from backend.ws.constants import (
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    ROLE_QUERY_PARAM,
    SESSION_QUERY_PARAM,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_MISSING_SESSION,
    WS_CLOSE_REASON_MAX_BYTES,
    WS_CLOSE_UNKNOWN_ROLE,
)
from backend.ws.dispatch import CommandSink, FrameDispatcher, WsClosure
from backend.ws.session import WsSession
from backend.ws.sink import WebSocketPreviewSink
from contracts.ws import WsRole


def truncate_close_reason(reason: str) -> str:
    """Cut a close reason to the RFC 6455 close-payload limit, on a character boundary.

    Truncating here rather than leaving it to the transport is the difference between a
    long refusal arriving shortened and arriving not at all: a close frame whose payload
    exceeds the limit is a protocol error, and the client would see a bare drop with no
    code instead of the reason it needs.

    Args:
        reason: The refusal text.

    Returns:
        (str) The reason, at most `WS_CLOSE_REASON_MAX_BYTES` bytes when UTF-8 encoded.
    """
    encoded = reason.encode("utf-8")
    if len(encoded) <= WS_CLOSE_REASON_MAX_BYTES:
        return reason
    return encoded[:WS_CLOSE_REASON_MAX_BYTES].decode("utf-8", errors="ignore")


def handshake_session(
    role_value: str | None,
    session_id: str | None,
    origin: str | None,
    allowed_origins: tuple[str, ...],
    preview_sink: WebSocketPreviewSink,
) -> WsSession | WsClosure:
    """Build the connection's session from its handshake parameters, or refuse it.

    Args:
        role_value: The `role` query parameter, or None when absent.
        session_id: The `session_id` query parameter, or None when absent.
        origin: The `Origin` header the browser stamped, or None when absent.
        allowed_origins: The exact origins the control-channel policy admits.
        preview_sink: This connection's binary TX surface.

    Returns:
        (WsSession | WsClosure) The session, or the close the handshake earned.
    """
    # Origin first, before anything about this client is believed. A WebSocket handshake
    # is exempt from the same-origin policy, so an unchecked endpoint is reachable from
    # any page the operator has open — and that page would inherit the soft stop, which
    # every role may send. An absent header is refused with the rest: a non-browser client
    # sends none, and this channel's callers are browsers (`FR-OPS-090`).
    if origin is None or origin not in allowed_origins:
        return WsClosure(
            code=WS_CLOSE_FORBIDDEN_ORIGIN,
            reason=f"origin {origin!r} is not on the control-channel allowlist",
        )
    if not session_id:
        return WsClosure(
            code=WS_CLOSE_MISSING_SESSION,
            reason=f"the {SESSION_QUERY_PARAM!r} query parameter is required",
        )
    # An absent role and an unrecognised one are refused identically, and the absent case
    # is named rather than left to `WsRole(None)` raising: a role this server cannot place
    # is a role it must not guess at, and defaulting an unnamed connection to the least
    # privileged role would still hand it the soft stop under an identity nobody assigned.
    if role_value is None or role_value not in set(WsRole):
        return WsClosure(
            code=WS_CLOSE_UNKNOWN_ROLE,
            reason=(
                f"unknown {ROLE_QUERY_PARAM} {role_value!r}; "
                f"one of {', '.join(member.value for member in WsRole)}"
            ),
        )
    return WsSession(role=WsRole(role_value), session_id=session_id, preview_sink=preview_sink)


def mount_realtime_channel(
    app: FastAPI,
    latch_target: LatchTarget,
    deadman: DeadmanController,
    clock: Clock,
    command_sink: CommandSink,
    security: ControlChannelSecurity,
) -> FastAPI:
    """Mount the single realtime websocket route on an existing application.

    `security` is required rather than defaulted, and it is read on every handshake. Both
    halves matter: `ControlChannelSecurity` cannot be constructed in a shape `FR-OPS-090`
    forbids, so demanding one makes the policy's existence a precondition of mounting at
    all; and checking the Origin against it in the handshake is what keeps the policy from
    being an object the code holds and never consults.

    Args:
        app: The application to add the route to. Supplied by the caller so the REST
            surface and this one can share an application, or not, as the host decides.
        latch_target: The arm's shared latch surface — the same object `deadman` drives.
        deadman: The lease canon (`WP-2A-02`).
        clock: The server monotonic clock latch timestamps are stamped from.
        command_sink: Where an authorised command frame goes.
        security: The control-channel transport policy (`FR-OPS-090`). Its WS half names
            the scheme and the Origin allowlist this route admits.

    Returns:
        (FastAPI) The same application, with the one realtime route mounted.
    """
    dispatcher = FrameDispatcher(
        latch_target=latch_target,
        deadman=deadman,
        clock=clock,
        command_sink=command_sink,
    )

    @app.websocket(REALTIME_ROUTE)
    async def realtime(websocket: WebSocket) -> None:
        """Serve one client: handshake, then decode-authorise-route until it goes away.

        The handshake is refused *after* `accept()` rather than before, so the client
        gets a close code and a reason it can read. A pre-accept rejection is delivered
        as a bare HTTP 403, in which a bad role, a missing session and a backend that is
        simply down are the same event.
        """
        await websocket.accept()
        sink = WebSocketPreviewSink(websocket)
        session = handshake_session(
            websocket.query_params.get(ROLE_QUERY_PARAM),
            websocket.query_params.get(SESSION_QUERY_PARAM),
            websocket.headers.get(ORIGIN_HEADER),
            security.ws.origin_allowlist,
            sink,
        )
        if isinstance(session, WsClosure):
            await websocket.close(code=session.code, reason=truncate_close_reason(session.reason))
            return

        # The preview drain is its own task because the two directions are independent:
        # a client that sends nothing must still receive camera frames, and a client
        # flooding the socket must not starve them. Cancelled in `finally`, so a
        # disconnect never leaves a task holding a closed socket.
        drain = asyncio.create_task(sink.drain_forever())
        try:
            while True:
                raw = await websocket.receive_text()
                outcome = dispatcher.dispatch(session, raw)
                if outcome.reply is not None:
                    await websocket.send_json(outcome.reply)
                if outcome.closure is not None:
                    await websocket.close(
                        code=outcome.closure.code,
                        reason=truncate_close_reason(outcome.closure.reason),
                    )
                    return
        except WebSocketDisconnect:
            return
        finally:
            drain.cancel()

    return app


__all__ = ["handshake_session", "mount_realtime_channel", "truncate_close_reason"]
