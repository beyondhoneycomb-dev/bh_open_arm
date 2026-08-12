"""Which bind addresses keep a plaintext control channel off the network (`NORM-015`).

`14` FR-OPS-090 requires WSS/TLS and forbids the plaintext schemes. `NORM-015` rules that the
requirement describes a channel exposed on a network, and admits plaintext for a loopback-bound
research deployment — on two conditions, of which this module owns the first: **a non-loopback
bind is refused before the server listens**. `oa-serve --host` is a flag, so without the refusal the
carve-out is a plaintext control channel one argument away from a LAN.

It lives in the security tree rather than beside the WebSocket deployment type because the two
are different concerns and one of them must not drag the other in. The address a server binds is
the server's, and `backend/config/serve.py` is held to naming no symbol from `backend/ws/**`
(`tests/wpg00_backend/test_serve.py`) so a WebSocket package under construction cannot stop the
REST surface and the SPA bundle from serving. The second condition — the Origin allowlist the
handshake reads — is the WebSocket deployment's and lives there.
"""

from __future__ import annotations

# The hosts a loopback bind may name. `localhost` is included because it is what an operator
# types; the OS resolves it to a loopback address, and the check below is on the bind address
# rather than on DNS.
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


class LoopbackBindError(ValueError):
    """Raised when a plaintext control channel is asked to bind an address that leaves the host."""


def is_loopback_host(host: str) -> bool:
    """Whether an address keeps a bound socket on this machine.

    Compared whole rather than by prefix: a prefix test would admit `127.0.0.1.evil.example`.

    Args:
        host: The address to judge.

    Returns:
        (bool) True when the address is one of the loopback hosts.
    """
    return host in LOOPBACK_HOSTS


def assert_loopback_bind(host: str) -> None:
    """Refuse to serve the plaintext control channel on an address that reaches the network.

    Args:
        host: The address the server was asked to bind.

    Raises:
        LoopbackBindError: When the address is not a loopback host. The message names what to do
            instead, because the alternative is not "try another port" — it is TLS.
    """
    if is_loopback_host(host):
        return
    raise LoopbackBindError(
        f"refusing to serve the plaintext control channel on {host!r}: only "
        f"{', '.join(LOOPBACK_HOSTS)} is admitted (NORM-015). A control channel reachable from "
        "the network requires WSS (14 FR-OPS-090)"
    )
