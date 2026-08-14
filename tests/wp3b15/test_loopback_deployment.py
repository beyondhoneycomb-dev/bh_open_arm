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
from contracts.ws import LEASE_SESSION_FIELD, WsFrameType, WsRole
from contracts.ws.schema import WsError, WsSecurityPolicy
from tests.wp3b15.conftest import DEFAULT_SESSION_ID, SafetyLatchTarget, expect_close

LOOPBACK_ORIGIN = f"http://{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}"

# An address that reaches the network. This is what `oa-serve --host` accepts today, which is why
# the refusal has to exist rather than being implied by a default.
ROUTABLE_HOST = "0.0.0.0"


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


def _mount_loopback_channel(allowlist: tuple[str, ...]) -> TestClient:
    """Mount the realtime route over a loopback deployment, on the production safety objects.

    Nothing safety-bearing is doubled: the latch is the production one-way `SafetyLatch` and
    the lease is the production `DeadmanController`, for the reason `conftest` gives. What is
    under test here is narrower — that the handshake reads THIS deployment's allowlist.

    Args:
        allowlist: The Origins the mounted route should admit.

    Returns:
        (TestClient) An in-process client over the mounted application; binds no port.
    """
    clock = ManualClock()
    target = SafetyLatchTarget(SafetyLatch())
    client = TestClient(FastAPI())
    mount_realtime_channel(
        client.app,
        latch_target=target,
        deadman=DeadmanController(
            lease=LeaseManager(DEADMAN_LEASE_DURATION_SEC), latch_target=target, clock=clock
        ),
        clock=clock,
        command_sink=_no_arm_session,
        security=LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=allowlist),
    )
    return client


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
    """
    with _mount_loopback_channel((LOOPBACK_ORIGIN,)) as client, _connect(client, LOOPBACK_ORIGIN):
        pass


def test_the_mounted_loopback_route_still_refuses_a_remote_origin() -> None:
    """Dropping TLS did not drop the check — the price is charged at the handshake, not only
    in the constructor.

    The allowlist passed here is a valid loopback one, so a refusal cannot come from the
    deployment refusing to be built. It comes from the connecting page's Origin, which is the
    threat `FR-OPS-090` names in its own rationale.
    """
    with (
        _mount_loopback_channel((LOOPBACK_ORIGIN,)) as client,
        _connect(client, "http://evil.example") as socket,
    ):
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
    with (
        _mount_loopback_channel((LOOPBACK_ORIGIN,)) as client,
        _connect(client, LOOPBACK_ORIGIN) as socket,
    ):
        socket.send_json({ENVELOPE_TYPE_FIELD: WsFrameType.COMMAND.value})
        refusal = expect_close(socket)

    assert refusal.code == WS_CLOSE_COMMAND_UNROUTABLE
    assert refusal.code != WS_CLOSE_UNAUTHORIZED_FRAME


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

    clock = ManualClock()
    target = SafetyLatchTarget(SafetyLatch())
    client = TestClient(FastAPI())
    mount_realtime_channel(
        client.app,
        latch_target=target,
        deadman=DeadmanController(
            lease=LeaseManager(DEADMAN_LEASE_DURATION_SEC), latch_target=target, clock=clock
        ),
        clock=clock,
        command_sink=_record,
        security=LoopbackDeployment(host=DEFAULT_HTTP_HOST, origin_allowlist=(LOOPBACK_ORIGIN,)),
    )

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
