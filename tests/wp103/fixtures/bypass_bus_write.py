"""A follower that bypasses the gateway and writes CAN directly — the acceptance-① violation.

Data, not logic: this file exists so the no-bypass scan has something to catch. It
reaches past the single gateway straight for the CAN write symbol, which is exactly
the bypass `11` NFR-INF-008 forbids, so `find_producer_can_access` must flag it.
"""

from __future__ import annotations


class BypassingFollower:
    """A follower whose send_action skips the gateway and writes the bus itself."""

    def send_action(self, action: dict[str, float]) -> None:
        """Reach past the gateway for the CAN write — the bypass the scan must catch."""
        self.bus._mit_control_batch(action)  # type: ignore[attr-defined]
