"""`NORM-015` — the plaintext deployment exists, and both halves of its price are charged.

The ruling is not "plaintext is fine". It is that TLS closes a threat a loopback bind does not
have, while the threat FR-OPS-090 actually names — any page writing control commands — is closed
by the Origin allowlist and is closed here too. So the tests that matter are the refusals: a bind
that leaves the machine, and an allowlist that would admit anything.

The networked policy is untouched and still refuses `ws://`; that is asserted here as well,
because a carve-out that quietly relaxed the other shape would be the softening `NORM-015`
declined to do.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.actuation.clock import ManualClock
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.config.constants import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT
from backend.deadman import DEADMAN_LEASE_DURATION_SEC, DeadmanController
from backend.security.loopback import LoopbackBindError, assert_loopback_bind
from backend.security.origin_policy import ControlChannelSecurity, RestCorsPolicy
from backend.ws import (
    ENVELOPE_TYPE_FIELD,
    ORIGIN_HEADER,
    REALTIME_ROUTE,
    WS_CLOSE_COMMAND_UNROUTABLE,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_UNAUTHORIZED_FRAME,
    WsClosure,
    WsSession,
    mount_realtime_channel,
)
from backend.ws.deployment import (
    DeploymentError,
    LoopbackDeployment,
    admitted_origins,
)
from backend.ws.dispatch import CommandSink
from contracts.ws import LEASE_SESSION_FIELD, WsFrameType, WsRole
from contracts.ws.schema import WsError, WsSecurityPolicy
from tests.wp3b15.conftest import (
    DEFAULT_SESSION_ID,
    SafetyLatchTarget,
    expect_close,
    stop_frame,
)

LOOPBACK_ORIGIN = f"http://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}"

# An address that reaches the network. This is what `oa-serve --host` accepts today, which is why
# the refusal has to exist rather than being implied by a default.
ROUTABLE_HOST = "0.0.0.0"

# The IPv6 loopback, spelled out rather than indexed out of `LOOPBACK_HOSTS`: what these tests
# pin is that this exact address survives the round trip through an Origin, and an index would
# follow a reordering of that tuple to a different address without failing.
IPV6_LOOPBACK_HOST = "::1"


def test_the_deployment_oa_serve_creates_can_now_be_described() -> None:
    """The loopback bind plus a loopback Origin builds — this is the blockage `NORM-015` cleared."""
    deployment = LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=(LOOPBACK_ORIGIN,))

    assert admitted_origins(deployment) == (LOOPBACK_ORIGIN,)


def test_a_routable_bind_is_refused_by_the_deployment() -> None:
    """The carve-out is loopback-only; naming a routable host in it is refused."""
    with pytest.raises(DeploymentError, match="not loopback"):
        LoopbackDeployment(host=ROUTABLE_HOST, origin_allowlist=(LOOPBACK_ORIGIN,))


def test_the_server_refuses_a_routable_bind_before_it_listens() -> None:
    """Obligation 1: without this, the carve-out is one argument away from a LAN."""
    with pytest.raises(LoopbackBindError, match="refusing to serve"):
        assert_loopback_bind(ROUTABLE_HOST)


def test_a_loopback_bind_is_admitted() -> None:
    """The refusal is not a blanket one, or `oa-serve` could never start."""
    assert_loopback_bind(DEFAULT_HTTP_HOST)


def test_an_empty_allowlist_is_refused() -> None:
    """Obligation 2. An empty allowlist admits any Origin, which is the whole threat."""
    with pytest.raises(DeploymentError, match="Origin allowlist is required"):
        LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=())


def test_a_wildcard_origin_is_refused() -> None:
    """Dropping TLS does not drop the Origin check; the wildcard is still forbidden."""
    with pytest.raises(DeploymentError, match="wildcard"):
        LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=("*",))


def test_a_remote_origin_is_refused_even_on_a_loopback_bind() -> None:
    """A page served from elsewhere must not be admitted to a socket answering on this machine."""
    with pytest.raises(DeploymentError, match="not a loopback origin"):
        LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=("http://evil.example",))


def test_a_remote_origin_that_merely_starts_with_a_loopback_name_is_refused() -> None:
    """The host is compared whole; a prefix match would admit `http://127.0.0.1.evil.example`."""
    with pytest.raises(DeploymentError, match="not a loopback origin"):
        LoopbackDeployment(
            host=DEFAULT_HTTP_HOST,
            origin_allowlist=(f"http://{DEFAULT_HTTP_HOST}.evil.example",),
        )


def test_the_networked_policy_still_refuses_plaintext() -> None:
    """`CTR-WS@v2` is not softened — a channel exposed on a network is still WSS-only."""
    with pytest.raises(WsError, match="wss"):
        WsSecurityPolicy(scheme="ws", origin_allowlist=(LOOPBACK_ORIGIN,), csrf_cors_enforced=True)


def test_userinfo_does_not_pass_a_remote_host_off_as_a_loopback_one() -> None:
    """The host of `http://127.0.0.1:8000@evil.example` is `evil.example` (RFC 3986 §3.2).

    Everything before the `@` is userinfo. An allowlist check that reads it as the host admits
    an entry whose page is served from anywhere, which is the single thing this validator exists
    to refuse. Exact-string matching at the handshake is what keeps the hole from being a door
    today — a defence this entry was never meant to need.
    """
    with pytest.raises(DeploymentError, match="not a loopback origin"):
        LoopbackDeployment(
            host=DEFAULT_HTTP_HOST,
            origin_allowlist=(f"http://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}@evil.example",),
        )


def test_an_ipv6_loopback_origin_is_admitted() -> None:
    """`::1` is a bind `assert_loopback_bind` admits, so its page's Origin must build too.

    A browser writes an IPv6 host in brackets. Refusing the bracketed form leaves a server that
    may bind `::1` unable to name the page it serves, which is a deployment with no allowlist it
    can pass — and `NORM-015` makes the allowlist the price of the plaintext scheme.
    """
    ipv6_origin = f"http://[{IPV6_LOOPBACK_HOST}]:{DEFAULT_HTTP_PORT}"

    deployment = LoopbackDeployment(host=IPV6_LOOPBACK_HOST, origin_allowlist=(ipv6_origin,))

    assert admitted_origins(deployment) == (ipv6_origin,)


def test_a_tls_terminated_loopback_page_is_admitted() -> None:
    """`https://` on loopback is stricter than the `http://` this deployment already takes.

    The scheme set is about which Origins a browser can stamp, not about what the channel is
    carried over: a page served over TLS on this machine sends `https://127.0.0.1:8000`, and
    refusing it says "not a loopback origin" about an origin that plainly is one.
    """
    tls_origin = f"https://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}"

    deployment = LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=(tls_origin,))

    assert admitted_origins(deployment) == (tls_origin,)


def test_an_unparsable_origin_is_refused_as_a_deployment_error() -> None:
    """A malformed entry earns this class's own refusal, not a bare parser exception.

    `http://[::1` — an unclosed IPv6 bracket, one keystroke from the form above — is what the
    operator gets wrong. Every other bad entry here is answered with a message naming the
    offending origin, and a `ValueError` escaping the parser instead would put a startup failure
    in front of them whose text is about URL syntax rather than about the allowlist they wrote.
    """
    with pytest.raises(DeploymentError, match="not a loopback origin"):
        LoopbackDeployment(
            host=DEFAULT_HTTP_HOST,
            origin_allowlist=(f"http://[{IPV6_LOOPBACK_HOST}",),
        )


def test_a_websocket_url_is_not_an_origin_and_is_refused() -> None:
    """No browser ever stamps `ws://` on an `Origin` header — it names the page, not the socket.

    Admitting the form is worse than useless: the operator writes the URL their client connects
    to, the deployment builds, and every handshake is then refused against an allowlist that
    matches no Origin any browser can produce.
    """
    with pytest.raises(DeploymentError, match="not a loopback origin"):
        LoopbackDeployment(
            host=DEFAULT_HTTP_HOST,
            origin_allowlist=(f"ws://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}",),
        )


def _mount_loopback_channel(
    allowlist: tuple[str, ...], command_sink: CommandSink
) -> tuple[TestClient, SafetyLatch]:
    """Mount the realtime route over a loopback deployment, on the production safety objects.

    Nothing safety-bearing is doubled: the latch is the production one-way `SafetyLatch` and
    the lease is the production `DeadmanController`, for the reason `conftest` gives. What is
    under test here is narrower — that the handshake reads THIS deployment's allowlist.

    Args:
        allowlist: The Origins the mounted route should admit.
        command_sink: Where a routed `command` frame goes. Passed rather than fixed because the
            two hosts this file distinguishes — one holding an arm, one holding none — differ in
            exactly this argument and in nothing else.

    Returns:
        (tuple) An in-process client over the mounted application, binding no port, and the one
        latch behind it. The latch is returned because a handshake that was admitted is only
        observable through something the connection did.
    """
    clock = ManualClock()
    latch = SafetyLatch()
    target = SafetyLatchTarget(latch)
    client = TestClient(FastAPI())
    mount_realtime_channel(
        client.app,
        latch_target=target,
        deadman=DeadmanController(
            lease=LeaseManager(DEADMAN_LEASE_DURATION_SEC), latch_target=target, clock=clock
        ),
        clock=clock,
        command_sink=command_sink,
        security=LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=allowlist),
    )
    return client, latch


def _no_arm_session(session: WsSession, payload: Mapping[str, Any]) -> WsClosure:
    """Refuse a command the way a host holding no arm must: visibly, never by dropping it."""
    return WsClosure(
        code=WS_CLOSE_COMMAND_UNROUTABLE,
        reason=f"no arm session for {session.session_id}: {sorted(payload)}",
    )


def _connect(client: TestClient, origin: str) -> Any:
    """Open one operator connection carrying the given Origin header."""
    return client.websocket_connect(
        f"{REALTIME_ROUTE}?role={WsRole.OPERATOR.value}&{LEASE_SESSION_FIELD}={DEFAULT_SESSION_ID}",
        headers={ORIGIN_HEADER: origin},
    )


def test_the_loopback_deployment_can_actually_mount_the_route() -> None:
    """The route mounts over the loopback shape and admits a page served from this machine.

    Every other test in this file judges the type. This one judges the handshake, and it is
    the one that fails if the mount reads the networked policy's `ws.origin_allowlist`
    directly instead of asking the deployment: `LoopbackDeployment` has no `ws` attribute, so
    that mount raises rather than admitting the wrong origin. Until this passed, `NORM-015`
    described a deployment nothing could serve.

    Admission is asserted through the latch rather than through the connection opening. A
    refused handshake is refused *after* `accept()`, so opening the socket succeeds either way
    and a test that only enters the context passes against a server that admits nobody — which
    is what this one did. What separates the two is whether a frame sent on the connection was
    acted on, and the soft stop is the frame this channel exists to carry.
    """
    client, latch = _mount_loopback_channel((LOOPBACK_ORIGIN,), _no_arm_session)

    with client, _connect(client, LOOPBACK_ORIGIN) as socket:
        socket.send_json(stop_frame())

    assert latch.is_active
    assert latch.reason is not None
    assert DEFAULT_SESSION_ID in latch.reason.gate_id


def test_the_mounted_loopback_route_still_refuses_a_remote_origin() -> None:
    """Dropping TLS did not drop the check — the price is charged at the handshake, not only
    in the constructor.

    The allowlist passed here is a valid loopback one, so a refusal cannot come from the
    deployment refusing to be built. It comes from the connecting page's Origin, which is the
    threat `FR-OPS-090` names in its own rationale.
    """
    client, _ = _mount_loopback_channel((LOOPBACK_ORIGIN,), _no_arm_session)

    with client, _connect(client, "http://evil.example") as socket:
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_FORBIDDEN_ORIGIN


def test_a_command_a_host_cannot_route_closes_instead_of_vanishing() -> None:
    """A sink with no arm behind it refuses where the operator can see it.

    This is the branch `oa-serve` is in today: the process serves the GUI and the arm is held
    by a separate CLI, so an authorised `command` reaches a host with nothing to command. The
    frame is well formed and the sender is entitled to send it, so the failure is neither
    malformed nor unauthorised — and if the dispatcher discarded what the sink returned, the
    operator would watch the command leave and nothing move, which is the one outcome
    `CommandSink` exists to make impossible.
    """
    client, _ = _mount_loopback_channel((LOOPBACK_ORIGIN,), _no_arm_session)

    with client, _connect(client, LOOPBACK_ORIGIN) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: WsFrameType.COMMAND.value})
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_COMMAND_UNROUTABLE


def test_the_unroutable_code_is_not_the_unauthorised_one() -> None:
    """The two refusals send the operator in opposite directions, so they may not share a code.

    Read as "unauthorised", a host with no arm sends the operator looking for a permission they
    already hold. The distinctness belongs to the constants; asserting it on a response would
    make the claim depend on which frame happened to be sent.
    """
    assert WS_CLOSE_COMMAND_UNROUTABLE != WS_CLOSE_UNAUTHORIZED_FRAME


def test_a_routing_host_is_unchanged_by_that_refusal_path() -> None:
    """A sink that did route returns None, and the connection stays open.

    The refusal above is a property of the sink, not of the frame type. A host that owns an
    arm must not inherit a close from it, or wiring the arm in would be a regression on the
    channel that already worked.
    """
    routed: list[str] = []

    def _record(session: WsSession, payload: Mapping[str, Any]) -> None:
        """The routing host's sink: consume the frame and refuse nothing."""
        routed.append(session.session_id)

    client, _ = _mount_loopback_channel((LOOPBACK_ORIGIN,), _record)

    with client, _connect(client, LOOPBACK_ORIGIN) as socket:
        socket.send_json({ENVELOPE_TYPE_FIELD: WsFrameType.COMMAND.value})
        socket.send_json({ENVELOPE_TYPE_FIELD: WsFrameType.COMMAND.value})

    assert routed == [DEFAULT_SESSION_ID, DEFAULT_SESSION_ID]


def test_both_shapes_answer_the_same_question_about_origins() -> None:
    """The handshake reads one allowlist whichever deployment it was handed."""
    networked = ControlChannelSecurity(
        ws=WsSecurityPolicy(
            scheme="wss", origin_allowlist=("https://arm.local",), csrf_cors_enforced=True
        ),
        rest=RestCorsPolicy(
            rest_scheme="https", allowed_origins=("https://arm.local",), csrf_enforced=True
        ),
    )
    loopback = LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=(LOOPBACK_ORIGIN,))

    assert admitted_origins(networked) == ("https://arm.local",)
    assert admitted_origins(loopback) == (LOOPBACK_ORIGIN,)
