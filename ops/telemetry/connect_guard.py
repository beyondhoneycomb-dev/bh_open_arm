"""F23 runtime guard — a second `connect()` destroys the established zero (`14` F23).

`14` F23: calling `Robot.connect()` again re-runs the driver's zeroing, silently discarding
the zero the session established. The danger surfaces on mode-transition paths, where it is
tempting to "just reconnect" when switching between teleop and playback. This guard makes the
re-call loud instead of silent: the first connect establishes the zero; any later connect
raises `ZeroingDestroyedError` rather than quietly re-zeroing.

`mode_transition` is the marker decorator the static counterpart keys on
(`connect_staticcheck`): annotating a transition handler both documents it and lets the scan
find `connect()` calls on that path even when the handler's name does not match the heuristic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

# Runtime marker set on a function annotated as a mode-transition handler. Read by tests and
# available for introspection; the static scan reads the decorator name from source instead.
MODE_TRANSITION_MARKER = "__oa_mode_transition__"


class ZeroingDestroyedError(RuntimeError):
    """`connect()` was called again after zeroing was already established (F23)."""


def mode_transition(func: F) -> F:
    """Mark a function as a mode-transition handler.

    Args:
        func: The transition handler.

    Returns:
        (F) The same function, tagged with the mode-transition marker.
    """
    setattr(func, MODE_TRANSITION_MARKER, True)
    return func


def is_mode_transition(func: Callable[..., Any]) -> bool:
    """Report whether a function was marked as a mode-transition handler.

    Args:
        func: Candidate function.

    Returns:
        (bool) True when the marker is present.
    """
    return bool(getattr(func, MODE_TRANSITION_MARKER, False))


class ZeroingConnectGuard:
    """Guards the connect/zeroing lifecycle so a re-connect cannot silently re-zero.

    Ownership/lifecycle: one guard per device session. The first `connect` establishes the
    zero; the guard then treats any further `connect` as the F23 fault and refuses it, so the
    established zero can never be discarded without an explicit disconnect first.
    """

    def __init__(self) -> None:
        self.m_connected = False
        self.m_zero_count = 0
        self.m_reconnect_attempts = 0

    @property
    def is_connected(self) -> bool:
        """Whether a connection (and thus a zero) is currently established.

        Returns:
            (bool) True after a successful first connect and before a disconnect.
        """
        return self.m_connected

    @property
    def zero_count(self) -> int:
        """How many times a zero has been established (never more than once per connect).

        Returns:
            (int) The count of established zeros.
        """
        return self.m_zero_count

    @property
    def reconnect_attempts(self) -> int:
        """How many rejected re-connect attempts were detected.

        Returns:
            (int) The count of F23 faults this guard caught.
        """
        return self.m_reconnect_attempts

    def connect(self, connect_fn: Callable[[], T]) -> T:
        """Run the first connect; reject any later one as an F23 fault.

        Args:
            connect_fn: Zero-argument callable that performs the actual connect/zeroing.

        Returns:
            (T) Whatever `connect_fn` returns on the first, accepted call.

        Raises:
            ZeroingDestroyedError: On any connect after the first; `connect_fn` is not run.
        """
        if self.m_connected:
            self.m_reconnect_attempts += 1
            raise ZeroingDestroyedError(
                "connect() re-called after zeroing was established; the established zero would "
                "be destroyed (F23) — disconnect explicitly before reconnecting"
            )
        result = connect_fn()
        self.m_connected = True
        self.m_zero_count += 1
        return result

    def disconnect(self) -> None:
        """Tear down the connection so a subsequent connect is legitimate again."""
        self.m_connected = False
