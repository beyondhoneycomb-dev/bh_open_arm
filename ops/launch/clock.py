"""Controlled clock for the simulated execution harness.

`WP-BOOT-04` is an `AI-offline` package: fake workflows, fault injection, controlled clock. Time
is a plain callable returning a float so that production code can pass `time.monotonic` and the
harness can pass this, without an interface existing for the sake of one test double.
"""

from __future__ import annotations


class ManualClock:
    """A clock that only moves when the harness moves it."""

    def __init__(self, start: float) -> None:
        self.value = start

    def __call__(self) -> float:
        """Read the current time.

        Returns:
            (float): The current clock value.
        """
        return self.value

    def advance(self, delta: float) -> float:
        """Move the clock forward.

        Args:
            delta: Amount to advance by.

        Returns:
            (float): The new clock value.
        """
        self.value += delta
        return self.value
