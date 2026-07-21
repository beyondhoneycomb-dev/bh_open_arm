"""State-transition tracking — the crash report's "last state transition" field.

`14` FR-OPS-024 lists the last state transition among the fields a crash report must carry:
knowing the machine died is far less useful than knowing it died one tick after leaving
`HOMING` for `TELEOP`. The log keeps the ordered history and, cheaply, the most recent
transition, because that last one is what the crash reporter reads back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StateTransition:
    """A single state change.

    Attributes:
        t: Monotonic seconds at which the transition occurred.
        from_state: State left.
        to_state: State entered.
    """

    t: float
    from_state: str
    to_state: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable form for the crash spool.

        Returns:
            (dict[str, Any]) `{t, from_state, to_state}`.
        """
        return {"t": self.t, "from_state": self.from_state, "to_state": self.to_state}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> StateTransition:
        """Rebuild a transition from its spooled dict.

        Args:
            data: A dict produced by `to_dict`.

        Returns:
            (StateTransition) The reconstructed transition.
        """
        return StateTransition(
            t=float(data["t"]),
            from_state=str(data["from_state"]),
            to_state=str(data["to_state"]),
        )


class StateTransitionLog:
    """Ordered history of state transitions with O(1) access to the most recent one."""

    def __init__(self) -> None:
        self.m_transitions: list[StateTransition] = []

    def record(self, t: float, from_state: str, to_state: str) -> StateTransition:
        """Append a transition and return it.

        Args:
            t: Monotonic seconds of the transition.
            from_state: State left.
            to_state: State entered.

        Returns:
            (StateTransition) The recorded transition.
        """
        transition = StateTransition(t=t, from_state=from_state, to_state=to_state)
        self.m_transitions.append(transition)
        return transition

    def last(self) -> StateTransition | None:
        """Return the most recent transition, or None if none has been recorded.

        Returns:
            (StateTransition | None) The last transition.
        """
        return self.m_transitions[-1] if self.m_transitions else None
