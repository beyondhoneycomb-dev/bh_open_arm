"""Pass fixture: `connect()` only on the initial path, never on a transition (F23).

Proves the scan does not over-fire. `initial_connect` is the legitimate first connect; the
mode-transition handler here changes state without reconnecting, so the scan must find nothing.
"""

from __future__ import annotations

from typing import Any

from ops.telemetry.connect_guard import mode_transition


def initial_connect(robot: Any) -> None:
    """The one legitimate connect — session start, not a transition."""
    robot.connect()


@mode_transition
def switch_to_playback(robot: Any) -> None:
    """Change mode without reconnecting — the correct shape."""
    robot.set_mode_playback()
