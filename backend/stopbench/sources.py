"""Source the stop-path boundary timestamps from the Wave 2A configuration primitives.

WP-2A-06 measures the stop path *under the Wave 2A configuration* (`02b` WP-2A-06 input
column names WP-2A-02 and WP-2A-05), and the two inputs are consumed differently on
purpose:

- The release boundary is the deadman lease's server-clock expiry, read here from the
  live `DeadmanLease.expiry_mono_server` (WP-2A-02). This is a real code reference — the
  capture-time adapter reads the sibling's own frozen value, it does not re-derive it.
- The scheduler boundary is the audit ring's record of the hold-emitting tick (WP-2A-05
  `AuditRecord.at`). WP-2A-05 declares that WP-2A-06 consumes it by a *capture-file
  timestamp join*, not a code import (`06` §5.6 justification on the WP-2A-05 row), so it
  arrives here as a plain float lifted from the capture, and this module deliberately does
  not import `backend.audit` — importing it would contradict that declaration.

This is the capture-time adapter: on the rig the caller holds the live lease and reads the
audit `at` from the capture, extracts the boundaries here, and the sample is serialised for
the deferred re-verification hook. The transmit and CAN-first-byte boundaries come from the
kernel-clock instrumentation `03` §5.7.0 requires, supplied by the caller.
"""

from __future__ import annotations

from backend.deadman import DeadmanLease
from backend.stopbench.decompose import StopPathSample


def release_boundary(lease: DeadmanLease) -> float:
    """Return the stop interval's start: the deadman lease's server-clock expiry (WP-2A-02).

    The server monotonic clock owns the expiry decision (U-4); its value is the release
    event that begins the stop path.

    Args:
        lease: The expired deadman lease.

    Returns:
        (float) `lease.expiry_mono_server`, seconds.
    """
    return lease.expiry_mono_server


def sample_from_2a_sources(
    *,
    lease: DeadmanLease,
    transmit_at: float,
    scheduler_at: float,
    can_write_at: float,
    can_first_byte_at: float,
) -> StopPathSample:
    """Build a stop-path sample from the deadman lease and the joined audit tick time.

    Args:
        lease: The expired deadman lease (WP-2A-02); its expiry is the release boundary.
        transmit_at: The transmit boundary, from the harness/transmit instrumentation.
        scheduler_at: The scheduler boundary — the audit ring's hold-tick `at` (WP-2A-05),
            joined from the capture rather than imported.
        can_write_at: The CAN-write boundary, from the rig instrumentation.
        can_first_byte_at: The CAN first-byte boundary, from the kernel-clock instrumentation.

    Returns:
        (StopPathSample) The five monotonic boundary timestamps on one clock domain.

    Raises:
        NonMonotonicSampleError: If the supplied boundaries are not monotonic.
    """
    return StopPathSample(
        lease_expiry_at=release_boundary(lease),
        transmit_at=transmit_at,
        scheduler_at=scheduler_at,
        can_write_at=can_write_at,
        can_first_byte_at=can_first_byte_at,
    )
