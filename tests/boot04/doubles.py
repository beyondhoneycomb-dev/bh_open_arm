"""Test doubles for the WP-BOOT-04 suite.

Kept out of `conftest.py` so test modules can import the type by a unique module name; several
sibling suites have a `conftest` of their own.
"""

from __future__ import annotations

from ops.cancel.executor import LATCH_TO_HOLD
from ops.cancel.scheduler import LatchReason


class RecordingScheduler:
    """Stand-in for the ActuationScheduler owned by WP-0A-01.

    The physical executor is not this package's to build; this records the call and its argument
    so the contract and its ordering can be asserted. It writes into the caller's shared log, so
    ordering is observed from the callee side rather than trusted from the executor's own trace.
    """

    def __init__(self, call_log: list[str]) -> None:
        self.call_log = call_log
        self.reasons: list[LatchReason] = []

    def latch_to_hold(self, reason: LatchReason) -> None:
        """Record a latch request.

        Args:
            reason: Cause and timestamp supplied by the cancellation executor.
        """
        self.call_log.append(LATCH_TO_HOLD)
        self.reasons.append(reason)
