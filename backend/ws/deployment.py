"""The two shapes a control channel may be deployed in, and what each has to prove (`NORM-015`).

`14` FR-OPS-090 requires WSS/TLS and forbids `ws://`. `01` §2.17 gives the web backend
`HTTP / WS` on 8000 and the row beneath it gives WebXR `HTTPS` on 8443 — the same table
assigning a plaintext form to one component and TLS to another. `NORM-015` rules that both
are right because they describe different deployments, and splits them here rather than by
softening `CTR-WS@v2`: that contract's frozen body carries `security.scheme = "wss"`, eleven
work packages consume it, and a channel exposed on a network really is WSS-only.

What separates the two is not a preference. TLS closes eavesdropping and tampering on the
wire; a loopback bind has no wire an attacker can stand on, and a process that could read
loopback traffic can already do worse. The threat FR-OPS-090 states in its own rationale is
different — *any browser or script writing control commands* — and that one is real here and
is closed by the Origin allowlist, not by TLS. A WebSocket handshake is not subject to the
same-origin policy: the browser sends it and the server decides. Without the allowlist, a page
the operator happens to have open connects to the arm's control socket.

So `LoopbackDeployment` drops TLS and keeps everything else, and it carries two obligations
that are the price of dropping it:

1. **The bind address is loopback, and a non-loopback bind is refused at startup.** That half
   lives in `backend.security.loopback` because the address a server binds is the server's, and
   `backend/config/serve.py` may not name a symbol from this tree (`tests/wpg00_backend`).
2. **The Origin allowlist is still required, and every entry is a loopback origin.** An empty
   allowlist admits any Origin, which is the failure mode above.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from backend.security.loopback import LOOPBACK_HOSTS, is_loopback_host
from backend.security.origin_policy import ControlChannelSecurity
from contracts.ws.schema import WILDCARD_ORIGIN

# The schemes an entry may carry. An allowlist holds Origins — what a browser stamps on the
# `Origin` header — and that value is the scheme, host and port of the *page*, never of the
# socket it opens. So both HTTP forms belong here and `ws://` does not: an operator who writes
# the URL their client connects to would build a deployment whose every handshake is refused
# against an allowlist no browser can match. `https://` is admitted because a locally
# TLS-terminated page is stricter than the `http://` this deployment already exists to take,
# and the host that follows is checked against `LOOPBACK_HOSTS` either way.
_ORIGIN_SCHEMES = ("http", "https")


class DeploymentError(ValueError):
    """Raised when a loopback deployment is described in a shape `NORM-015` forbids."""


def _origin_host(origin: str) -> str | None:
    """Return the host an origin names, or None when it is not one of the admitted schemes.

    Parsed rather than sliced, because the two shapes that break a hand-written split are both
    ones this validator has to get right. `http://[::1]:8000` writes an IPv6 host in brackets,
    and `::1` is a bind `assert_loopback_bind` admits — a server that may bind it must be able
    to name its own page. And in `http://127.0.0.1:8000@evil.example` everything before the `@`
    is userinfo (RFC 3986 §3.2), so the host is `evil.example`; reading the userinfo as the host
    admits a remote page, which is the one thing this check exists to refuse.

    Args:
        origin: An Origin header value.

    Returns:
        (str | None) The host without its port or brackets, or None when the scheme is not one
        a browser can stamp on an Origin.
    """
    try:
        split = urlsplit(origin)
    except ValueError:
        # An unclosed bracket (`http://[::1`) is rejected by the parser itself, before any
        # field exists to judge. It is answered as "no host" so the caller's refusal names the
        # origin the operator typed, rather than a URL-syntax traceback out of startup.
        return None
    if split.scheme not in _ORIGIN_SCHEMES:
        return None
    return split.hostname


@dataclass(frozen=True)
class LoopbackDeployment:
    """A plaintext control channel that never leaves the machine (`NORM-015`).

    Attributes:
        host: The bind address; must be a loopback host.
        origin_allowlist: The exact Origins the handshake admits. Required and non-empty for
            the same reason the networked policy requires it, and every entry must itself be
            a loopback origin — an allowlist that named a remote origin would admit a page
            served from elsewhere to a socket that answers on this machine.
    """

    host: str
    origin_allowlist: tuple[str, ...]

    def __post_init__(self) -> None:
        """Refuse a non-loopback bind, an empty or wildcard allowlist, or a remote origin."""
        if not is_loopback_host(self.host):
            raise DeploymentError(
                f"host {self.host!r} is not loopback; a plaintext control channel is admitted "
                f"only on {', '.join(LOOPBACK_HOSTS)} (NORM-015). Bind elsewhere and the "
                "channel needs WSS (14 FR-OPS-090)"
            )
        if not self.origin_allowlist:
            raise DeploymentError(
                "an Origin allowlist is required; an empty allowlist admits any Origin, and a "
                "WebSocket handshake is not subject to the same-origin policy"
            )
        if WILDCARD_ORIGIN in self.origin_allowlist:
            raise DeploymentError(
                "a wildcard Origin is forbidden; the allowlist must name exact Origins"
            )
        for origin in self.origin_allowlist:
            host = _origin_host(origin)
            if host is None or not is_loopback_host(host):
                raise DeploymentError(
                    f"Origin {origin!r} is not a loopback origin; this deployment admits only "
                    f"pages served from {', '.join(LOOPBACK_HOSTS)}"
                )


ControlChannelDeployment = ControlChannelSecurity | LoopbackDeployment


def admitted_origins(deployment: ControlChannelDeployment) -> tuple[str, ...]:
    """Return the Origin allowlist the handshake checks against, whichever shape was given.

    Both shapes are matched by name rather than one being the fallback for "not the other".
    Nothing type-checks this argument — `backend/` is in no mypy gate — so an object of a third
    kind would otherwise reach `.ws` and raise `AttributeError` at the first handshake, inside
    an accepted socket, naming a field instead of the argument the host got wrong.

    Args:
        deployment: The networked policy or the loopback one.

    Returns:
        (tuple[str, ...]) The exact Origins admitted.

    Raises:
        TypeError: If the argument is neither deployment shape.
    """
    if isinstance(deployment, LoopbackDeployment):
        return deployment.origin_allowlist
    if isinstance(deployment, ControlChannelSecurity):
        return deployment.ws.origin_allowlist
    raise TypeError(
        f"a control channel is deployed as a ControlChannelSecurity or a LoopbackDeployment; "
        f"got {type(deployment).__name__}"
    )
