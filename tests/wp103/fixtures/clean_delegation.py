"""A follower that delegates to the gateway — no CAN handle reached (the clean case).

The counter-fixture to `bypass_bus_write`: its send_action names no CAN write symbol,
so the no-bypass scan must NOT flag it. Its presence proves the scan discriminates
rather than flagging every file beside a violation.
"""

from __future__ import annotations


class CleanFollower:
    """A follower whose send_action routes through the gateway and touches no bus."""

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        """Delegate to the single gateway; no CAN handle is named here."""
        return self.gateway.submit(action)  # type: ignore[attr-defined,no-any-return]
