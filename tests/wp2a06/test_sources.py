"""The Wave 2A source adapter: the release boundary is the deadman lease.

WP-2A-06's input column declares WP-2A-02 (deadman lease) and WP-2A-05 (audit ring). The
lease is consumed by code reference — the release boundary is read from a genuine
`DeadmanLease.expiry_mono_server` — so these exercise that real dependency rather than a
stand-in. The audit tick time is joined from the capture file (WP-2A-05's `06` §5.6
declaration that WP-2A-06 does not import `backend.audit`), so it enters the adapter as a
plain float, which is what `sample_from_2a_sources` takes for `scheduler_at`.
"""

from __future__ import annotations

import pytest

from backend.deadman import DeadmanLease
from backend.stopbench import (
    StopPathSegment,
    release_boundary,
    sample_from_2a_sources,
)


def _lease(expiry_mono_server: float) -> DeadmanLease:
    """Build a deadman lease expired at the given server time.

    Args:
        expiry_mono_server: The server-clock expiry, seconds.

    Returns:
        (DeadmanLease) A lease carrying that expiry.
    """
    return DeadmanLease(
        generation=1,
        expiry_mono_server=expiry_mono_server,
        sequence=1,
        issued_mono_client=0.0,
    )


def test_release_boundary_is_the_lease_expiry() -> None:
    assert release_boundary(_lease(1.5)) == 1.5


def test_sample_from_2a_sources_reads_the_lease_expiry() -> None:
    sample = sample_from_2a_sources(
        lease=_lease(1.000),
        transmit_at=1.002,
        scheduler_at=1.003,
        can_write_at=1.006,
        can_first_byte_at=1.010,
    )
    # The release boundary came from the lease; the scheduler boundary is the joined value.
    assert sample.lease_expiry_at == 1.000
    assert sample.scheduler_at == 1.003
    durations = sample.segment_durations()
    assert durations[StopPathSegment.HARNESS_EVENT] == pytest.approx(0.002)
    assert durations[StopPathSegment.SCHEDULER] == pytest.approx(0.003)
    assert sample.reconciles()
