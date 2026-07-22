"""The payload registry: the single source of truth for what payload is on the arm now.

There is one end-effector, so at most one payload is registered at a time; registering
replaces the current one and unregistering clears to "no payload". The gravity reflection
(`PayloadGravityModel`) reads this registry, so the whole subsystem agrees on one answer to
"what mass is mounted", which is the property FR-MAN-033 needs — an unregistered or stale
payload is a constant residual offset that reads as a permanent false or missed collision.

Ownership/threading: a registry is mutated and read from one thread — the actuation or
preflight loop that owns it. Build one per consumer; do not share across threads.
"""

from __future__ import annotations

from backend.payload.payload import Payload


class PayloadRegistry:
    """Holds the single currently-registered end-effector payload, or none."""

    def __init__(self) -> None:
        """Start with no payload registered (the bare arm plus its default end-effector)."""
        self._payload: Payload | None = None

    def register(self, payload: Payload) -> None:
        """Register `payload` as the mounted payload, replacing any previous one.

        Args:
            payload: The validated payload now on the arm. Validation happened at its
                construction, so an invalid payload cannot reach this method.
        """
        self._payload = payload

    def unregister(self) -> None:
        """Clear the registered payload back to "no payload"."""
        self._payload = None

    def current(self) -> Payload | None:
        """Return the registered payload, or None when nothing is registered."""
        return self._payload

    def is_registered(self) -> bool:
        """Return whether a payload is currently registered."""
        return self._payload is not None
