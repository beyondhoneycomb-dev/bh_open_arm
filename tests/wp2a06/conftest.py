"""Shared fixtures for the WP-2A-06 suite: a trusted clock and a synthetic sample set.

The samples are hand-built boundary timestamps on one clock domain — the honest offline
basis the decomposition machinery runs on. The clock provenance is a kernel-timestamping
record, the one `03` §5.7.0 accepts, so the reused WP-1-05 builder publishes rather than
refuses; the refusal paths get their own bad-clock inputs in the tests that exercise them.
"""

from __future__ import annotations

import pytest

from backend.stopbench import StopPathSample
from backend.torque_bringup import ClockProvenance
from backend.torque_bringup.constants import CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING


def make_sample(
    base_sec: float,
    harness_sec: float,
    transmit_sec: float,
    scheduler_sec: float,
    can_sec: float,
) -> StopPathSample:
    """Build a stop-path sample from a start time and four segment durations.

    Args:
        base_sec: The lease-expiry boundary, seconds.
        harness_sec: Harness-event segment duration.
        transmit_sec: Transmit segment duration.
        scheduler_sec: Scheduler segment duration.
        can_sec: CAN segment duration.

    Returns:
        (StopPathSample) The five monotonic boundary timestamps.
    """
    transmit_at = base_sec + harness_sec
    scheduler_at = transmit_at + transmit_sec
    can_write_at = scheduler_at + scheduler_sec
    return StopPathSample(
        lease_expiry_at=base_sec,
        transmit_at=transmit_at,
        scheduler_at=scheduler_at,
        can_write_at=can_write_at,
        can_first_byte_at=can_write_at + can_sec,
    )


@pytest.fixture
def synthetic_samples() -> list[StopPathSample]:
    """A small set of synthetic stop-path samples with a known per-segment split.

    Returns:
        (list[StopPathSample]) Twenty samples, each 2/1/3/4 ms across the four stages.
    """
    return [make_sample(index * 0.001, 0.002, 0.001, 0.003, 0.004) for index in range(20)]


@pytest.fixture
def valid_clock() -> ClockProvenance:
    """A trusted kernel-timestamping clock provenance (`03` §5.7.0 method A).

    Returns:
        (ClockProvenance) A provenance the reused WP-1-05 builder accepts.
    """
    return ClockProvenance(
        method=CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING,
        offset_sec=1e-6,
        uncertainty_sec=1e-7,
    )
