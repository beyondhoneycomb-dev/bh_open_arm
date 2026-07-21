"""Service bind-address policy — local by default, non-local needs confirmation.

FR-SYS-026 and the 02a §6 contract: a service binds to a local address unless a
user explicitly confirms exposure. `0.0.0.0` (all interfaces) is exposure, not a
local address, so it is gated behind the same explicit-confirmation discipline the
upload path uses — an unconfirmed non-local request is refused, not silently bound.
"""

from __future__ import annotations

# The exact set of hosts this policy treats as loopback-only. The all-interfaces
# wildcard address is not a member: it binds every interface, which is the exposure
# the confirmation gates.
LOCAL_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_BIND_HOST = "127.0.0.1"


class NonLocalBindingError(Exception):
    """A non-local bind address was requested without explicit confirmation."""

    def __init__(self, host: str) -> None:
        super().__init__(
            f"bind host {host!r} exposes the service beyond localhost; "
            "explicit confirmation is required"
        )
        self.host = host


def is_local(host: str) -> bool:
    """Report whether a host binds the loopback interface only."""
    return host in LOCAL_HOSTS


def resolve_bind_host(requested: str | None, confirmed: bool = False) -> str:
    """Return the effective bind host under the local-default policy.

    Args:
        requested: The host the caller asked for, or None when unspecified.
        confirmed: Whether the user explicitly confirmed a non-local exposure.

    Returns:
        (str) The host to bind. Unspecified resolves to the local default.

    Raises:
        NonLocalBindingError: A non-local host was requested without confirmation.
    """
    if requested is None:
        return DEFAULT_BIND_HOST
    if is_local(requested):
        return requested
    if not confirmed:
        raise NonLocalBindingError(requested)
    return requested
