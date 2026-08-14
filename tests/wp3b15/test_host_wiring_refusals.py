"""A host that wires this channel wrongly finds out at the wiring, not inside a live socket.

Both surfaces here are handed objects by the host: `mount_realtime_channel` takes a deployment,
and `FrameDispatcher` calls back into a sink the host wrote. Neither is checked by any gate —
`scripts/gates.sh` runs mypy over `registry ops dashboard` and `scripts`, and `backend/` is in
none of them — so the annotations on both are documentation, and a host that ignores one gets no
warning until a browser is already connected.

That is the failure worth refusing. A refusal raised inside the connection task lands after
`accept()`, and the client sees an abnormal close with no code and no reason — the one outcome
`app.py` says the post-accept design exists to avoid, because in it a bad wiring, a refused
frame and a backend that is simply down are the same event.

The module already answers this shape for server-authored frames: `_envelope` checks a reply's
fields against `FRAME_TABLE` and raises rather than letting a browser read a missing key as a
null. These are the same check on the two objects that arrive from outside.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest

from backend.actuation.clock import ManualClock
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.deadman import DEADMAN_LEASE_DURATION_SEC, DeadmanController
from backend.ws import WsSession
from backend.ws.deployment import admitted_origins
from backend.ws.dispatch import FrameDispatcher
from backend.ws.sink import WebSocketPreviewSink
from contracts.ws import WsError, WsFrameType, WsRole
from tests.wp3b15.conftest import DEFAULT_SESSION_ID, SafetyLatchTarget, frame

# What a sink written against the previous `-> None` contract hands back when its author reaches
# for the obvious return value. It is truthy, so `DispatchOutcome.closure` carries it and the
# connection handler asks it for a `.code`.
SINK_RETURNING_A_BOOL = True

COMMAND_FRAME_TEXT = json.dumps(frame(WsFrameType.COMMAND))


def _dispatcher(sink: Any) -> FrameDispatcher:
    """Build the dispatcher over the production safety objects and the given sink."""
    clock = ManualClock()
    target = SafetyLatchTarget(SafetyLatch())
    return FrameDispatcher(
        latch_target=target,
        deadman=DeadmanController(
            lease=LeaseManager(DEADMAN_LEASE_DURATION_SEC), latch_target=target, clock=clock
        ),
        clock=clock,
        command_sink=sink,
    )


def _operator_session() -> WsSession:
    """An authorised session with no preview surface.

    `WebSocketPreviewSink` binds the running event loop in its constructor, and these tests drive
    the dispatcher directly — data in, decision out, no socket and no loop. The field is absent
    rather than doubled because no path under test reads it, and a stand-in would be a second
    thing to keep true.
    """
    return WsSession(
        role=WsRole.OPERATOR,
        session_id=DEFAULT_SESSION_ID,
        preview_sink=cast(WebSocketPreviewSink, None),
    )


def test_a_sink_returning_something_other_than_a_closure_is_refused_at_the_route() -> None:
    """The widened return type is a contract, and nothing else in this process enforces it.

    Carried through untouched, a bool reaches the connection handler as `outcome.closure` and
    dies on `.code` — inside the websocket task, after accept, as a bare drop. Raised here it
    names the sink's return and the frame, on the first command rather than on the first command
    that mattered.
    """
    dispatcher = _dispatcher(lambda _session, _payload: SINK_RETURNING_A_BOOL)

    with pytest.raises(WsError, match="WsClosure"):
        dispatcher.dispatch(_operator_session(), COMMAND_FRAME_TEXT)


def test_a_sink_that_routed_still_reports_nothing() -> None:
    """The refusal above must not turn a routing host's `None` into an error."""
    routed: list[Mapping[str, Any]] = []

    def _record(_session: WsSession, payload: Mapping[str, Any]) -> None:
        """The routing host's sink: consume the frame and refuse nothing."""
        routed.append(payload)

    outcome = _dispatcher(_record).dispatch(_operator_session(), COMMAND_FRAME_TEXT)

    assert outcome.closure is None
    assert outcome.reply is None
    assert len(routed) == 1


def test_a_deployment_of_neither_shape_is_refused_by_name() -> None:
    """`admitted_origins` may not treat "not loopback" as "has a `ws` allowlist".

    The fallback reads `.ws.origin_allowlist` off whatever it was given, so an object of a third
    kind raises `AttributeError` at the first handshake — inside the accepted socket, naming a
    field rather than the argument that was wrong.
    """
    with pytest.raises(TypeError, match="ControlChannelSecurity"):
        admitted_origins(cast(Any, object()))
