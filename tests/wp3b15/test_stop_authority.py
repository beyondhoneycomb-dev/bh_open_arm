"""The soft stop reaches the latch from every role; a command reaches it from one.

This is the pair `CG-G-01g` and `13` FR-GUI-065 ask for together, and the point is that
they are the *same* connection: the observer whose `command` the server refuses is the
observer whose `stop_hold` engages the latch. Testing them apart would pass just as well
on a server that had accidentally made the stop a control frame and hidden the failure
behind a second, more privileged fixture.

Nothing here reads a flag the server set. The assertion is `SafetyLatch.is_active` and
`SafetyLatch.reason` on the production latch object the server was built over, so a stop
that engaged something else would fail rather than pass on a mirror.

Ordering is a queue fact, not a timing one: `TestClient` appends each send to the ASGI
receive queue the connection handler drains in order, and closing the socket appends the
disconnect behind them. So a stop sent before the block exits has been handled by the
time the block exits, with nothing slept on.
"""

from __future__ import annotations

import pytest

from backend.ws import GUI_STOP_GATE_PREFIX, WS_CLOSE_UNAUTHORIZED_FRAME
from contracts.ws import CONTROL_HOLDER_ROLE, WsFrameType, WsRole
from tests.wp3b15.conftest import (
    DEFAULT_SESSION_ID,
    WsFixture,
    connect,
    expect_close,
    frame,
    stop_frame,
)


def test_observer_stop_hold_engages_the_shared_latch(ws: WsFixture) -> None:
    """An observer — holding no command authority — still stops the arm (FR-GUI-065)."""
    assert not ws.latch.is_active
    with connect(ws, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())
    assert ws.latch.is_active


def test_observer_command_is_refused_on_the_connection_whose_stop_works(
    ws: WsFixture,
) -> None:
    """The same observer connection: stop accepted, command refused server-side (CG-G-01g)."""
    with connect(ws, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())
        socket.send_json(frame(WsFrameType.COMMAND))
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_UNAUTHORIZED_FRAME
    assert WsRole.OBSERVER.value in refusal.reason
    assert CONTROL_HOLDER_ROLE.value in refusal.reason
    # The stop that preceded the refusal still took effect. The two travel the same
    # socket and the authority check sits between them, so a server that had gated the
    # stop on authority too would leave the latch clear here.
    assert ws.latch.is_active
    assert ws.commands == []


def test_operator_command_reaches_the_host_sink(ws: WsFixture) -> None:
    """The one role holding command authority gets its command routed, unchanged."""
    payload = frame(WsFrameType.COMMAND)
    with connect(ws, WsRole.OPERATOR) as socket:
        socket.send_json(payload)

    assert ws.commands == [payload]
    assert [session.role for session in ws.sessions] == [WsRole.OPERATOR]
    assert not ws.latch.is_active


@pytest.mark.parametrize("role", list(WsRole))
def test_every_role_can_stop(ws: WsFixture, role: WsRole) -> None:
    """Observer, operator and admin all reach the latch — the stop gates on no authority."""
    with connect(ws, role) as socket:
        socket.send_json(stop_frame())
    assert ws.latch.is_active, f"{role.value} could not stop the arm"


def test_stop_is_attributed_to_this_surface_and_this_session(ws: WsFixture) -> None:
    """The latch reason names the GUI stop and who pressed it, on the server's clock."""
    ws.clock.advance(4.5)
    with connect(ws, WsRole.OBSERVER) as socket:
        socket.send_json(stop_frame())

    reason = ws.latch.reason
    assert reason is not None
    assert reason.gate_id == f"{GUI_STOP_GATE_PREFIX}:{DEFAULT_SESSION_ID}"
    assert reason.latched_at == 4.5


def test_repeated_stops_keep_the_first_attribution(ws: WsFixture) -> None:
    """Idempotent: a second stop changes nothing, including who is blamed for the first."""
    with connect(ws, WsRole.OBSERVER, session_id="first-presser") as socket:
        socket.send_json(stop_frame("first-presser"))
    first = ws.latch.reason

    ws.clock.advance(10.0)
    with connect(ws, WsRole.ADMIN, session_id="second-presser") as socket:
        socket.send_json(stop_frame("second-presser"))

    assert ws.latch.is_active
    assert ws.latch.reason == first
