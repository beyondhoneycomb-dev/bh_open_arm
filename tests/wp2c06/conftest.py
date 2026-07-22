"""Shared fixtures for the WP-2C-06 suite: a trusted clock and a synthetic sample set.

The samples are hand-built boundary timestamps on one clock domain — the honest offline
basis the decomposition machinery runs on. The clock provenance is a kernel-timestamping
record, the one `03` §5.7.0 accepts, so the bench publishes rather than refuses; the refusal
paths get their own bad-clock inputs in the tests that exercise them.
"""

from __future__ import annotations

import pytest

from backend.reaction_bench import ReactionSample
from backend.torque_bringup import ClockProvenance
from backend.torque_bringup.constants import CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING


def make_sample(
    base_sec: float,
    select_sec: float,
    schedule_sec: float,
    can_sec: float,
) -> ReactionSample:
    """Build a reaction sample from a start time and three segment durations.

    Args:
        base_sec: The detection-confirm boundary, seconds.
        select_sec: Select segment duration (confirm -> reaction selected).
        schedule_sec: Schedule segment duration (selected -> scheduler write).
        can_sec: CAN segment duration (scheduler write -> first byte).

    Returns:
        (ReactionSample) The four monotonic boundary timestamps.
    """
    reaction_select_at = base_sec + select_sec
    scheduler_write_at = reaction_select_at + schedule_sec
    return ReactionSample(
        detection_confirm_at=base_sec,
        reaction_select_at=reaction_select_at,
        scheduler_write_at=scheduler_write_at,
        can_first_byte_at=scheduler_write_at + can_sec,
    )


@pytest.fixture
def synthetic_samples() -> list[ReactionSample]:
    """A small set of synthetic reaction samples with a known per-segment split.

    Returns:
        (list[ReactionSample]) Twenty samples, each 2/3/4 ms across the three stages.
    """
    return [make_sample(index * 0.001, 0.002, 0.003, 0.004) for index in range(20)]


@pytest.fixture
def valid_clock() -> ClockProvenance:
    """A trusted kernel-timestamping clock provenance (`03` §5.7.0 method A).

    Returns:
        (ClockProvenance) A provenance the bench accepts.
    """
    return ClockProvenance(
        method=CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING,
        offset_sec=1e-6,
        uncertainty_sec=1e-7,
    )
