"""A clamp counter that surfaces jog-path saturation as a tally, never a silent log.

Ownership: a mutable per-session tally owned by one `JogClampPath`, on the caller's
thread. LeRobot clips a `max_relative_target` overflow with `logger.debug` and moves
on, so the fact that a command was altered never reaches a consumer (`04` FR-MAN-013,
acceptance ③). This counter is the opposite: every clamp increments a per-reason
count a caller can read, so saturation is observable rather than lost to a log line
no one watches.
"""

from __future__ import annotations

from backend.jogclamp.reason import JogClampReason


class ClampCounter:
    """Per-reason tally of jog-path clamps, seeded to zero for every reason.

    Ownership: mutable state owned by a single `JogClampPath`; not thread-safe, which
    matches the jog path — one producer publishes on one thread.
    """

    def __init__(self) -> None:
        """Start every reason's count at zero so a read is never a missing key."""
        self._counts: dict[JogClampReason, int] = dict.fromkeys(JogClampReason, 0)

    def record(self, reason: JogClampReason) -> None:
        """Increment the tally for one clamp reason.

        Args:
            reason: The stage that altered the command this call.
        """
        self._counts[reason] += 1

    def count(self, reason: JogClampReason) -> int:
        """Return how many times a given clamp reason has fired.

        Args:
            reason: The reason to read.

        Returns:
            (int) The tally for that reason.
        """
        return self._counts[reason]

    @property
    def total(self) -> int:
        """The number of clamps across all reasons."""
        return sum(self._counts.values())

    def as_dict(self) -> dict[str, int]:
        """Return the tally keyed by reason value, for surfacing to a consumer.

        Returns:
            (dict[str, int]) One entry per reason, its string value to its count.
        """
        return {reason.value: count for reason, count in self._counts.items()}
