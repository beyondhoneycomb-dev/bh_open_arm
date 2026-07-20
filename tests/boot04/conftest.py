"""Shared fixtures for the WP-BOOT-04 suite.

The recording scheduler and the fake workflows write into ONE shared call log. Ordering
assertions are therefore made against what the callees observed, not against what the executor
reported about itself — an executor that latched in the wrong order could still narrate the
right order into its own trace.
"""

from __future__ import annotations

import pytest

from ops.cancel.scheduler import LatchReason
from ops.launch.clock import ManualClock
from tests.boot04.doubles import RecordingScheduler

CLOCK_START = 1000.0


@pytest.fixture
def call_log() -> list[str]:
    """Provide the shared ordering log.

    Returns:
        (list[str]): Empty log for one test.
    """
    return []


@pytest.fixture
def scheduler(call_log: list[str]) -> RecordingScheduler:
    """Provide a recording scheduler bound to the shared log.

    Args:
        call_log: Shared ordering log.

    Returns:
        (RecordingScheduler): The double.
    """
    return RecordingScheduler(call_log)


@pytest.fixture
def clock() -> ManualClock:
    """Provide a controlled clock.

    Returns:
        (ManualClock): Clock starting at a fixed value.
    """
    return ManualClock(CLOCK_START)


@pytest.fixture
def latch_reason() -> LatchReason:
    """Provide a latch reason with the four P-0 evidence fields populated.

    Returns:
        (LatchReason): Reason for use in cancellation tests.
    """
    return LatchReason(
        gate_id="PG-SAFE-001",
        previous_state="PASS",
        new_state="FAIL_BLOCKING",
        latched_at=CLOCK_START,
    )
