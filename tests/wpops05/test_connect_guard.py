"""Acceptance ⑦ (runtime half) — a re-`connect()` is detected, not silently re-zeroed (F23).

The runtime guard establishes the zero on the first connect and refuses any later one. A mode
transition that tries to reconnect trips it, so the F23 fault surfaces as a raised error rather
than a quietly discarded zero.
"""

from __future__ import annotations

import pytest

from ops.telemetry.connect_guard import (
    ZeroingConnectGuard,
    ZeroingDestroyedError,
    is_mode_transition,
    mode_transition,
)


def test_first_connect_establishes_the_zero() -> None:
    """The first connect runs the opener and establishes exactly one zero."""
    guard = ZeroingConnectGuard()
    calls: list[str] = []
    result = guard.connect(lambda: calls.append("open") or "handle")
    assert result == "handle"
    assert calls == ["open"]
    assert guard.is_connected
    assert guard.zero_count == 1


def test_second_connect_is_rejected_and_opener_not_run() -> None:
    """A re-connect raises and never runs the opener — the established zero is preserved."""
    guard = ZeroingConnectGuard()
    guard.connect(lambda: "first")
    opened: list[str] = []

    with pytest.raises(ZeroingDestroyedError):
        guard.connect(lambda: opened.append("second") or "second")

    assert opened == []
    assert guard.zero_count == 1
    assert guard.reconnect_attempts == 1


def test_reconnect_during_a_mode_transition_is_the_f23_fault() -> None:
    """A transition handler that reconnects trips the guard — the exact F23 scenario."""
    guard = ZeroingConnectGuard()
    guard.connect(lambda: "session")

    @mode_transition
    def switch_to_teleop() -> None:
        guard.connect(lambda: "reconnect")

    with pytest.raises(ZeroingDestroyedError):
        switch_to_teleop()


def test_disconnect_then_connect_is_legitimate() -> None:
    """After an explicit disconnect, a fresh connect is allowed again."""
    guard = ZeroingConnectGuard()
    guard.connect(lambda: "first")
    guard.disconnect()
    guard.connect(lambda: "second")
    assert guard.zero_count == 2


def test_marker_decorator_is_introspectable() -> None:
    """The `@mode_transition` marker is visible at runtime for introspection."""

    @mode_transition
    def handler() -> None:
        return None

    assert is_mode_transition(handler)

    def plain() -> None:
        return None

    assert not is_mode_transition(plain)
