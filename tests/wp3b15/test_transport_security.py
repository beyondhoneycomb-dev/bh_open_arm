"""WP-3B-15 — the control channel admits only allowlisted origins (`FR-OPS-090`).

A WebSocket handshake is not covered by the browser's same-origin policy: the browser
sends it and leaves the decision to the server. So an endpoint that does not read the
`Origin` header is reachable from any page the operator happens to have open, and that
page inherits everything this channel carries — including the soft stop, which every
role may send by design (`13` FR-GUI-065). The allowlist is what stands there instead.

`mount_realtime_channel` takes the policy as a required argument, and
`ControlChannelSecurity` cannot be constructed in a shape `FR-OPS-090` forbids, so the
policy's existence is a precondition of mounting. These tests cover the other half: that
the policy is read on every handshake rather than held and never consulted.
"""

from __future__ import annotations

import inspect

import pytest

from backend.config.constants import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT
from backend.security.constants import PLAINTEXT_HTTP_SCHEME
from backend.security.origin_policy import ControlChannelSecurity
from backend.ws import (
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_UNKNOWN_ROLE,
    mount_realtime_channel,
)
from contracts.ws import (
    LEASE_SESSION_FIELD,
    WS_PLAINTEXT_SCHEME,
    WS_SECURE_SCHEME,
    WsError,
    WsRole,
    WsSecurityPolicy,
)
from tests.wp3b15.conftest import (
    ALLOWED_ORIGIN,
    DEFAULT_SESSION_ID,
    FORBIDDEN_ORIGIN,
    WsFixture,
    connect,
    expect_close,
)


def test_an_allowlisted_origin_is_admitted(ws: WsFixture) -> None:
    """The permitted origin connects and stays open — the check refuses, it does not block."""
    with connect(ws, WsRole.OPERATOR, origin=ALLOWED_ORIGIN) as socket:
        assert socket is not None


def test_a_foreign_origin_is_refused(ws: WsFixture) -> None:
    """A page on another host may not open the control channel."""
    with connect(ws, WsRole.OBSERVER, origin=FORBIDDEN_ORIGIN) as socket:
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_FORBIDDEN_ORIGIN
    assert FORBIDDEN_ORIGIN in refusal.reason


def test_an_absent_origin_is_refused(ws: WsFixture) -> None:
    """No header is refused like a foreign one, rather than treated as trusted.

    An absent `Origin` is what a non-browser client sends, and this channel's callers are
    browsers. Admitting the absence would leave the allowlist trivially bypassable by any
    client that simply omits the header.
    """
    with connect(ws, WsRole.OPERATOR, origin=None) as socket:
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_FORBIDDEN_ORIGIN


def test_origin_is_judged_before_anything_the_client_claims(ws: WsFixture) -> None:
    """A foreign origin is refused as an origin, not as whatever else is wrong with it.

    The ordering is the point: role and session id are assertions the connecting client
    makes about itself, and none of them should be believed — or even parsed into a
    refusal reason the client reads back — before the origin has earned a hearing.
    """
    url = f"{REALTIME_ROUTE}?role=superuser&{LEASE_SESSION_FIELD}={DEFAULT_SESSION_ID}"
    with ws.client.websocket_connect(url, headers={ORIGIN_HEADER: FORBIDDEN_ORIGIN}) as socket:
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_FORBIDDEN_ORIGIN
    assert refusal.code != WS_CLOSE_UNKNOWN_ROLE


def test_no_policy_exists_for_the_plaintext_deployment_oa_serve_creates() -> None:
    """`oa-serve`'s own transport cannot be described by the policy this route requires.

    This is the standing record of an unresolved disagreement between two canonical
    documents, kept as a test so it cannot be forgotten and cannot be quietly worked
    around:

    - `01` §2.17 lists the web backend (SPA + REST + WebSocket, port 8000) as `HTTP / WS`,
      and the row beneath it gives WebXR `HTTPS` — so the same [확정] table distinguishes a
      TLS component from a plaintext one and assigns this port the plaintext form.
    - `14` FR-OPS-090 requires the control channel on WSS/TLS only and forbids `ws://`
      outright, with no loopback carve-out anywhere in `01`, `13`, `14` or `16`.

    `oa-serve` binds plain HTTP on loopback, so a WebSocket mounted there is `ws://`, and
    the policy `mount_realtime_channel` requires cannot be constructed to describe it. The
    route is therefore not mounted in `backend/config/serve.py`. Deleting this test to make
    the mount possible would be deciding the disagreement by removing its evidence.
    """
    with pytest.raises(WsError) as refused:
        WsSecurityPolicy(
            scheme=WS_PLAINTEXT_SCHEME,
            origin_allowlist=(
                f"{PLAINTEXT_HTTP_SCHEME}://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}",
            ),
            csrf_cors_enforced=True,
        )

    assert WS_SECURE_SCHEME in str(refused.value)


def test_the_route_requires_a_policy_it_cannot_be_given_a_forbidden_one() -> None:
    """Mounting demands the policy object, so no route exists without a valid one.

    The two halves together are what make the requirement un-skippable: the type refuses a
    forbidden shape, and the mount refuses to run without the type. A caller cannot mount
    the channel and enforce nothing.
    """
    # `eval_str` because `backend/ws/app.py` carries `from __future__ import annotations`,
    # which leaves every annotation a string; comparing the string would pass on a
    # different class that happened to share the name.
    signature = inspect.signature(mount_realtime_channel, eval_str=True)
    security = signature.parameters["security"]
    assert security.default is inspect.Parameter.empty
    assert security.annotation is ControlChannelSecurity
