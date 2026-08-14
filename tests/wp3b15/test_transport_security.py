"""WP-3B-15 — the control channel admits only allowlisted origins (`FR-OPS-090`).

A WebSocket handshake is not covered by the browser's same-origin policy: the browser
sends it and leaves the decision to the server. So an endpoint that does not read the
`Origin` header is reachable from any page the operator happens to have open, and that
page inherits everything this channel carries — including the soft stop, which every
role may send by design (`13` FR-GUI-065). The allowlist is what stands there instead.

`mount_realtime_channel` takes the deployment as a required argument, and neither shape it
admits can be constructed in a form its own ruling forbids — `ControlChannelSecurity`
refuses a plaintext scheme (`FR-OPS-090`), `LoopbackDeployment` refuses a routable bind or
a remote origin (`NORM-015`) — so a valid policy's existence is a precondition of mounting.
These tests cover the other half: that the policy is read on every handshake rather than
held and never consulted.
"""

from __future__ import annotations

import inspect
from typing import get_args

import pytest

from backend.config.constants import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT
from backend.security.constants import PLAINTEXT_HTTP_SCHEME
from backend.security.origin_policy import ControlChannelSecurity
from backend.ws import (
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_UNKNOWN_ROLE,
    ControlChannelDeployment,
    DeploymentError,
    LoopbackDeployment,
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


def test_the_networked_policy_still_refuses_a_plaintext_scheme() -> None:
    """`CTR-WS@v2` was not softened when `NORM-015` cleared the plaintext deployment.

    This test used to be the standing record of an unresolved disagreement — `01` §2.17 giving the
    web backend `HTTP / WS` on 8000 against `14` FR-OPS-090 forbidding `ws://` outright. `NORM-015`
    resolved it by splitting the deployment rather than the scheme: a channel exposed on a network
    is still WSS-only and this refusal is what holds that, while the loopback-bound research
    deployment is described by `backend.ws.deployment.LoopbackDeployment` and pays for dropping TLS
    with a refused non-loopback bind and a still-mandatory Origin allowlist
    (`tests/wp3b15/test_loopback_deployment.py`).

    So the assertion is unchanged and its meaning is not: it now pins that the carve-out did not
    leak into the shape it was carved out of.
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
    """Mounting demands a deployment object, so no route exists without a valid one.

    The two halves together are what make the requirement un-skippable: every shape the
    parameter admits refuses a forbidden form in its own constructor, and the mount refuses
    to run without one of them. A caller cannot mount the channel and enforce nothing.

    The annotation is compared against the union rather than one member because `NORM-015`
    split the deployment instead of softening the contract. Enumerating the members is the
    point of the second assertion: a third shape added here would have to prove it refuses
    its own forbidden form before this test would pass, so the parameter cannot quietly
    widen into something that enforces nothing.
    """
    # `eval_str` because `backend/ws/app.py` carries `from __future__ import annotations`,
    # which leaves every annotation a string; comparing the string would pass on a
    # different class that happened to share the name.
    signature = inspect.signature(mount_realtime_channel, eval_str=True)
    security = signature.parameters["security"]
    assert security.default is inspect.Parameter.empty
    assert security.annotation is ControlChannelDeployment
    assert set(get_args(security.annotation)) == {ControlChannelSecurity, LoopbackDeployment}


def test_every_admitted_deployment_refuses_its_own_forbidden_form() -> None:
    """Neither member of the union can be constructed in the shape its ruling forbids.

    This is the half the signature check rests on. Widening the parameter is only safe
    while every shape behind it is un-constructible when wrong: the networked policy on a
    plaintext scheme, and the loopback one on an allowlist that names a remote origin — the
    two ways a control channel becomes reachable from a page nobody vetted.
    """
    with pytest.raises(WsError):
        WsSecurityPolicy(
            scheme=WS_PLAINTEXT_SCHEME,
            origin_allowlist=(f"{PLAINTEXT_HTTP_SCHEME}://{DEFAULT_HTTP_HOST}",),
            csrf_cors_enforced=True,
        )
    with pytest.raises(DeploymentError):
        LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=("http://evil.example",))
