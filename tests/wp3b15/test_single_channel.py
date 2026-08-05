"""Exactly one realtime channel, and no parallel stack alongside it (`CTR-WS@v2` D-2).

D-2 permits one realtime browser<->backend transport. A second websocket route would be
a second channel whether or not anything used it yet, so the count is asserted on the
mounted application's own route table rather than on intent.

The forbidden parallel stacks are checked against this package's source rather than its
routes: `webrtc`, `foxglove`, `rosbridge` and `grpc-web` would not appear as ASGI routes
even if something opened one, so a route-table check would report clean on exactly the
violation it exists to catch.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIWebSocketRoute

import backend.ws
from backend.ws import REALTIME_ROUTE, WsSession, mount_realtime_channel
from contracts.ws import FORBIDDEN_PARALLEL_STACKS, REALTIME_CHANNEL
from tests.wp3b15.conftest import TEST_CONTROL_SECURITY, WsFixture


def _websocket_routes(app: FastAPI) -> list[APIWebSocketRoute]:
    """The websocket routes an application carries.

    `APIWebSocketRoute` rather than starlette's `WebSocketRoute` base: it is the exact
    type `@app.websocket` registers, and it is FastAPI's own surface, so this test names
    no package the project does not depend on directly.
    """
    return [route for route in app.router.routes if isinstance(route, APIWebSocketRoute)]


def _ignore_command(session: WsSession, payload: Mapping[str, Any]) -> None:
    """A command sink for an application this test never sends a command to."""


def test_mounting_adds_exactly_one_websocket_route(ws: WsFixture) -> None:
    """One mount, one realtime endpoint, at the declared path."""
    routes = _websocket_routes(ws.client.app)
    assert len(routes) == 1
    assert routes[0].path == REALTIME_ROUTE


def test_the_channel_is_the_websocket_the_contract_names(ws: WsFixture) -> None:
    """The one channel is `CTR-WS@v2`'s `websocket`, not a second transport beside it."""
    assert REALTIME_CHANNEL == "websocket"
    assert len(_websocket_routes(ws.client.app)) == 1


def test_mounting_twice_is_not_how_a_second_channel_appears(ws: WsFixture) -> None:
    """A caller that mounts onto a fresh app gets one route there too, not two here.

    The guard this states: the route is added to the application handed in, so a host
    holding one application cannot end up with two realtime endpoints by calling the
    mount from two places unless it deliberately passes the same app twice — which the
    count above would catch.
    """
    other = FastAPI()
    mount_realtime_channel(
        other,
        latch_target=ws.target,
        deadman=ws.deadman,
        clock=ws.clock,
        command_sink=_ignore_command,
        security=TEST_CONTROL_SECURITY,
    )
    assert len(_websocket_routes(other)) == 1
    assert len(_websocket_routes(ws.client.app)) == 1


def test_no_forbidden_parallel_stack_is_opened_in_this_package() -> None:
    """None of the stacks D-2 forbids appears in the WS package's own sources."""
    package_file = backend.ws.__file__
    assert package_file is not None
    package_dir = Path(package_file).parent
    sources = {
        path.name: path.read_text(encoding="utf-8").lower() for path in package_dir.rglob("*.py")
    }
    assert sources, "the WS package has no sources to scan"
    for stack in FORBIDDEN_PARALLEL_STACKS:
        offenders = sorted(name for name, text in sources.items() if stack in text)
        assert offenders == [], f"{stack!r} appears in {offenders}"
