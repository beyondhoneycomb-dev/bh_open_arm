"""An E-Stop wired to `record_loop`'s `stop_recording` — the acceptance-② violation.

Scanning this must find the episode-control wiring: the safety stop must be the loop
changing what it sends, never leaving the loop via `stop_recording` (`FR-SAF-073`,
`12` §2.7.2). This fixture does the banned thing so the scan
(`backend.reaction.find_estop_stop_recording_wiring`) can be shown to bite.
"""

from __future__ import annotations

from typing import Any


def wrong_estop(events: dict[str, Any], scheduler: Any) -> None:
    """Treat the episode `stop_recording` event as an E-Stop — the banned shape.

    Args:
        events: The `record_loop()` events dict; reading `stop_recording` as a stop is
            the violation.
        scheduler: A scheduler the fixture wrongly latches from an episode event.
    """
    if events["stop_recording"]:
        scheduler.engage_safety_latch(None)
