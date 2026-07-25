"""Shared fixtures for the WP-5-08 acceptance tests.

The one lease under test is the real `backend.deadman` `DeadmanController` wired onto
the real `backend.actuation` `LeaseManager` and a `ManualClock`; the only test double
is the latch target, which stands in for the scheduler's `SafetyLatch` surface the
deadman drives. That double implements the exact `LatchTarget` protocol the real
`ActuationScheduler` satisfies, so the deadman code path exercised here is the
production one.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation.clock import ManualClock
from backend.actuation.lease import LeaseManager
from backend.deadman.controller import DeadmanController
from backend.deadman.messages import LeaseRenewal
from ops.cancel.scheduler import LatchReason

LEASE_DURATION_SEC = 0.1


class RecordingLatch:
    """A `LatchTarget` double that records engage/acknowledge, mirroring the scheduler.

    Structurally identical to the `ActuationScheduler` surface the deadman drives:
    `engage_safety_latch`, `acknowledge_latch`, and `latch_active`. It counts engages
    so a test can see the auto-hold fire, and keeps the first reason like the real
    one-way `SafetyLatch`.
    """

    def __init__(self) -> None:
        """Create an un-latched recording latch."""
        self._active = False
        self.engage_count = 0
        self.acknowledge_count = 0
        self.last_reason: LatchReason | None = None

    @property
    def latch_active(self) -> bool:
        """Whether the latch is currently held."""
        return self._active

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the latch, recording the engage and the (first) reason."""
        self.engage_count += 1
        if not self._active:
            self._active = True
            self.last_reason = reason

    def acknowledge_latch(self) -> None:
        """Clear the latch — an operator/re-arm action."""
        self.acknowledge_count += 1
        self._active = False


@dataclass(frozen=True)
class DeadmanFixture:
    """The one lease and the pieces around it, for a test.

    Attributes:
        clock: The manual server clock the whole fixture reads.
        lease: The single `LeaseManager` the controller renews and a guard reads.
        controller: The deadman controller (generation + expiry-latch).
        latch: The recording latch the deadman drives.
    """

    clock: ManualClock
    lease: LeaseManager
    controller: DeadmanController
    latch: RecordingLatch


def build_deadman(lease_duration_sec: float = LEASE_DURATION_SEC) -> DeadmanFixture:
    """Build the one deadman lease wired onto a manual clock and a recording latch.

    Args:
        lease_duration_sec: The lease horizon a renewal grants.

    Returns:
        (DeadmanFixture) The clock, lease, controller and latch, all sharing one clock.
    """
    clock = ManualClock()
    lease = LeaseManager(lease_duration_sec)
    latch = RecordingLatch()
    controller = DeadmanController(
        lease=lease,
        latch_target=latch,
        clock=clock,
        lease_duration_sec=lease_duration_sec,
    )
    return DeadmanFixture(clock=clock, lease=lease, controller=controller, latch=latch)


def take_deadman(fixture: DeadmanFixture, sequence: int = 1) -> None:
    """Take the deadman for its current generation: send one accepted renewal.

    Args:
        fixture: The deadman fixture.
        sequence: The renewal sequence to send (strictly increasing per generation).
    """
    now = fixture.clock.now()
    renewal = LeaseRenewal(
        generation=fixture.controller.current_generation,
        sequence=sequence,
        issued_mono_client=now,
    )
    result = fixture.controller.receive_renewal(renewal)
    assert result.accepted, f"setup renewal was not accepted: {result.decision}"


def latch_reason(at: float) -> LatchReason:
    """Build a latch reason for a forced-release or expiry HOLD.

    Args:
        at: The server-clock timestamp to stamp the latch with.

    Returns:
        (LatchReason) A reason attributing the latch to a WP-5-08 action.
    """
    return LatchReason(
        gate_id="WP-5-08",
        previous_state="LIVE",
        new_state="LATCHED",
        latched_at=at,
    )
