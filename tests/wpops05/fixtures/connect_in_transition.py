"""Violation fixture: `connect()` called on mode-transition paths (F23).

Proves `find_connect_in_mode_transition` bites. `switch_to_teleop` is marked with the
`@mode_transition` decorator; `enter_mode_playback` is caught by its name alone. Both re-run
zeroing on a transition path, the exact F23 fault the scan must flag.
"""

from __future__ import annotations

from typing import Any

from ops.telemetry.connect_guard import mode_transition


@mode_transition
def switch_to_teleop(robot: Any) -> None:
    """Reconnect on a transition path — destroys the established zero (forbidden)."""
    robot.connect()


def enter_mode_playback(robot: Any) -> None:
    """Reconnect on a name-detected transition path (forbidden)."""
    robot.connect()
