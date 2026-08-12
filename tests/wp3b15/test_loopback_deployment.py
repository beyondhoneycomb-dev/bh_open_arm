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

import pytest

from backend.config.constants import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT
from backend.security.loopback import LoopbackBindError, assert_loopback_bind
from backend.security.origin_policy import ControlChannelSecurity, RestCorsPolicy
from backend.ws.deployment import (
    DeploymentError,
    LoopbackDeployment,
    admitted_origins,
)
from contracts.ws.schema import WsError, WsSecurityPolicy

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
