"""Every refusal is visible, and each one is a distinct code.

The property under test is not "the server survives bad input" — it is that a client can
tell *which* thing was wrong. A single refusal code, or a silent drop, leaves a broken
client with a frame that never took effect and no way to learn that. So each case here
asserts the exact close code and that the reason names the thing refused.

`CTR-WS@v2` declares no server-to-client error frame, so a refusal is delivered as a
WebSocket close: to the browser, `onclose(code, reason)`. The close codes live in
`backend.ws.constants`, in RFC 6455's 4000-4999 private range.
"""

from __future__ import annotations

import pytest

from backend.ws import (
    ENVELOPE_TYPE_FIELD,
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    WS_CLOSE_MALFORMED_FRAME,
    WS_CLOSE_MISSING_SESSION,
    WS_CLOSE_UNKNOWN_FRAME_TYPE,
    WS_CLOSE_UNKNOWN_ROLE,
    WS_CLOSE_WRONG_DIRECTION,
    truncate_close_reason,
)
from backend.ws.constants import WS_CLOSE_REASON_MAX_BYTES
from contracts.ws import LEASE_SESSION_FIELD, WsFrameType, WsRole
from tests.wp3b15.conftest import (
    ALLOWED_ORIGIN,
    DEFAULT_SESSION_ID,
    WsFixture,
    connect,
    expect_close,
    frame,
)


def test_unknown_frame_type_is_refused_and_named(ws: WsFixture) -> None:
    """A tag with no `CTR-WS@v2` row is refused, and the reason lists what this channel carries."""
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: "torque_off"})
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_UNKNOWN_FRAME_TYPE
    assert "torque_off" in refusal.reason


def test_frame_that_is_not_json_is_refused(ws: WsFixture) -> None:
    """Undecodable text never reaches a handler, and the client is told it was not JSON."""
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_text("{not json")
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_MALFORMED_FRAME


def test_json_that_is_not_an_object_is_refused(ws: WsFixture) -> None:
    """A bare array carries no tag, so there is nothing to route it by."""
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json([WsFrameType.STOP_HOLD.value])
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_MALFORMED_FRAME
    assert ENVELOPE_TYPE_FIELD in refusal.reason
    assert not ws.latch.is_active


def test_object_without_a_string_tag_is_refused(ws: WsFixture) -> None:
    """A numeric tag is not a frame type; it is refused rather than coerced."""
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: 3})
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_MALFORMED_FRAME


@pytest.mark.parametrize(
    "server_frame",
    [
        WsFrameType.TELEMETRY,
        WsFrameType.CAMERA,
        WsFrameType.LEASE_GRANT,
        WsFrameType.LEASE_REJECT,
        WsFrameType.REARM_ISSUE,
        WsFrameType.REARM_ACCEPT,
    ],
)
def test_client_may_not_send_a_server_to_client_frame(
    ws: WsFixture, server_frame: WsFrameType
) -> None:
    """Direction is checked before authority, so a non-control server frame cannot slip through.

    `telemetry` and `camera` are marked `is_control_frame=False`, so an authority-first
    order would admit a client pushing either of them at the server.
    """
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: server_frame.value})
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_WRONG_DIRECTION
    assert server_frame.value in refusal.reason


def test_malformed_lease_renew_is_refused_rather_than_given_a_lease_reason(
    ws: WsFixture,
) -> None:
    """A broken frame is not a lease decision; spending a canon reason on it would mislead."""
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(frame(WsFrameType.LEASE_RENEW, **{LEASE_SESSION_FIELD: "s"}))
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_MALFORMED_FRAME


def test_unknown_role_is_refused_at_the_handshake(ws: WsFixture) -> None:
    """A role outside `WsRole` gets a readable close, not an opaque HTTP rejection."""
    url = f"{REALTIME_ROUTE}?role=superuser&{LEASE_SESSION_FIELD}={DEFAULT_SESSION_ID}"
    with ws.client.websocket_connect(url, headers={ORIGIN_HEADER: ALLOWED_ORIGIN}) as socket:
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_UNKNOWN_ROLE
    assert "superuser" in refusal.reason


def test_missing_session_id_is_refused_at_the_handshake(ws: WsFixture) -> None:
    """A connection with no session id could stop the arm and leave no attribution."""
    url = f"{REALTIME_ROUTE}?role={WsRole.OBSERVER.value}"
    with ws.client.websocket_connect(url, headers={ORIGIN_HEADER: ALLOWED_ORIGIN}) as socket:
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_MISSING_SESSION
    assert LEASE_SESSION_FIELD in refusal.reason


def test_a_long_reason_is_truncated_to_the_close_payload_limit() -> None:
    """An over-long reason arrives shortened rather than not at all (RFC 6455 §5.5.1)."""
    short = "refused"
    assert truncate_close_reason(short) == short

    long_reason = "가" * 200
    truncated = truncate_close_reason(long_reason)
    assert len(truncated.encode("utf-8")) <= WS_CLOSE_REASON_MAX_BYTES
    assert long_reason.startswith(truncated)
