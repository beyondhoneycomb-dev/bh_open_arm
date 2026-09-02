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
from collections.abc import Mapping

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.actuation.board import ArmStateBoard
from backend.actuation.clock import Clock
from backend.config.constants import CONTROL_TICK_HZ_DEFAULT
from backend.deadman import DeadmanController, LatchTarget
from backend.ws.constants import (
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    ROLE_QUERY_PARAM,
    SESSION_QUERY_PARAM,
    TELEMETRY_STALE_TICK_MULTIPLE,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_MISSING_SESSION,
    WS_CLOSE_REASON_MAX_BYTES,
    WS_CLOSE_UNKNOWN_ROLE,
    WS_PUBLISH_RATE_DEFAULT_HZ,
)
from backend.ws.deployment import ControlChannelDeployment, admitted_origins
from backend.ws.dispatch import CommandSink, FrameDispatcher, WsClosure, server_envelope
from backend.ws.session import WsSession
from backend.ws.sink import WebSocketPreviewSink
from backend.ws.telemetry import telemetry_body
from contracts.ws import WsFrameType, WsRole


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


# How often a connected client is sent the board's state, and how old a reading may be before
# the frame says so. `13` FR-GUI-004 wants the GUI to show what the arm is doing, not every tick
# of it: the control loop runs at 100 Hz and a socket carrying that would spend the link on
# frames no screen repaints for. The rate is `NFR-GUI-003`'s confirmed default rather than a
# figure chosen here — a publisher that picks its own number is a third answer to a question the
# spec and the frontend had already settled.
DEFAULT_TELEMETRY_HZ = WS_PUBLISH_RATE_DEFAULT_HZ
DEFAULT_STALE_AFTER_SEC = TELEMETRY_STALE_TICK_MULTIPLE / CONTROL_TICK_HZ_DEFAULT


async def _push_telemetry(
    websocket: WebSocket,
    boards: Mapping[str, ArmStateBoard],
    telemetry_hz: float,
    stale_after_s: float,
) -> None:
    """Send the board's state to one client until the connection goes away.

    Its own task because the two directions are independent: a client that sends nothing must
    still receive state, and one flooding the socket must not starve it. Cancelled in the
    handler's `finally`, so a disconnect never leaves a task writing to a closed socket.

    Every board is read in one pass and the frame is built from that pass, so one frame
    describes one instant. Reading them again per section would let the observation vector and
    the arm ages come from different ticks.

    This loop keeps running when the loop that FILLS the boards has stopped, and it must: a
    client that stops receiving cannot tell a dead reader from a dead link, and the two want
    opposite responses. What it sends instead is the board's age against `stale_after_s`, so a
    frozen board arrives labelled as one rather than as a robot holding perfectly still.

    A send that raises ends the loop rather than retrying. The socket is gone, and a task that
    kept trying would hold the connection's objects alive behind a client that left.
    """
    period = 1.0 / telemetry_hz
    try:
        while True:
            views = {side: board.view() for side, board in boards.items()}
            body = telemetry_body(views, stale_after_s)
            await websocket.send_json(server_envelope(WsFrameType.TELEMETRY, body))
            await asyncio.sleep(period)
    except (WebSocketDisconnect, RuntimeError):
        return


def mount_realtime_channel(
    app: FastAPI,
    latch_target: LatchTarget,
    deadman: DeadmanController,
    clock: Clock,
    command_sink: CommandSink,
    security: ControlChannelDeployment,
    boards: Mapping[str, ArmStateBoard] | None = None,
    telemetry_hz: float = DEFAULT_TELEMETRY_HZ,
    stale_after_s: float = DEFAULT_STALE_AFTER_SEC,
) -> FastAPI:
    """Mount the single realtime websocket route on an existing application.

    `security` is required rather than defaulted, and it is read on every handshake. Both
    halves matter: neither deployment shape can be constructed in a form its own ruling
    forbids — `ControlChannelSecurity` refuses a plaintext scheme (`FR-OPS-090`) and
    `LoopbackDeployment` refuses a non-loopback origin (`NORM-015`) — so demanding one makes
    the policy's existence a precondition of mounting at all; and checking the Origin against
    it in the handshake is what keeps the policy from being an object the code holds and never
    consults.

    What the deployment does NOT prove is the address the process actually binds. It validates
    its own `host` field, and a caller is free to describe a loopback deployment and then serve
    the application on a routable interface. `NORM-015`'s other obligation is charged where the
    socket is opened — `assert_loopback_bind` in `backend/config/serve.py` — so a host mounting
    this route by itself owes that check itself.

    The parameter is the union rather than the networked policy alone because `NORM-015`
    split the deployment instead of softening the contract. A loopback-bound research host
    admits the plaintext scheme and still owes the allowlist, and it needs a route to mount on.

    Args:
        app: The application to add the route to. Supplied by the caller so the REST
            surface and this one can share an application, or not, as the host decides.
        latch_target: The arm's shared latch surface — the same object `deadman` drives.
        deadman: The lease canon (`WP-2A-02`).
        clock: The server monotonic clock latch timestamps are stamped from.
        command_sink: Where an authorised command frame goes. A sink that cannot route
            one returns the close the client is owed rather than swallowing it.
        security: The control-channel deployment — the networked policy (`FR-OPS-090`) or
            the loopback one (`NORM-015`). Only its Origin allowlist is read here; the
            scheme is the deployment's own business and each shape already refused the
            schemes it may not carry.

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
            admitted_origins(security),
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
        # Only when this process holds boards. A connection with none sends nothing unprompted,
        # which is what lets a refusal test read the close it is owed as the FIRST message on
        # the socket: a telemetry frame arriving before it would be indistinguishable, to that
        # reader, from a server that answered instead of closing.
        pushing = (
            None
            if boards is None
            else asyncio.create_task(
                _push_telemetry(websocket, boards, telemetry_hz, stale_after_s)
            )
        )
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
            if pushing is not None:
                pushing.cancel()

    return app


__all__ = ["handshake_session", "mount_realtime_channel", "truncate_close_reason"]
