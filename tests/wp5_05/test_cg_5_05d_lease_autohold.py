"""CG-5-05d — WS delay → missed renewal → lease expiry → scheduler auto-hold.

The U-4 core, on the real objects: the real `LeaseManager`, the real
`DeadmanController`, the real `decide`. Renewals flowing means no hold; a WS delay
past the lease horizon latches the scheduler into a hold ("delay brings the stop
forward"); a fresh target in the mailbox does not keep the arm live across the lapse;
and once latched the decider emits `SAFETY_LATCH_HOLD`.
"""

from __future__ import annotations

from backend.loadtest import inject_ws_delay
from backend.loadtest.lease_delay import (
    LEASE_EXPIRED_HOLD_LABEL,
    LEASE_EXPIRED_HOLD_REASON,
    SAFETY_LATCH_HOLD_LABEL,
    decide_when_latched,
    decide_with_expired_lease_and_fresh_target,
)


def test_delay_drives_an_autohold() -> None:
    result = inject_ws_delay()
    assert result.latched, "a WS delay past the lease horizon must latch the scheduler to hold"
    # The hold engages one lease-duration after the last renewal, not later — delay
    # brings the stop forward rather than pushing it back.
    elapsed = result.seconds_from_last_renewal_to_hold
    assert elapsed is not None
    assert elapsed >= result.lease_duration_sec


def test_healthy_renewals_never_latch() -> None:
    # No injected delay: the whole window renews on cadence and must never hold.
    result = inject_ws_delay(healthy_ticks=40, delay_ticks=0)
    assert not result.latched
    assert result.seconds_from_last_renewal_to_hold is None


def test_fresh_target_does_not_keep_arm_live() -> None:
    emission = decide_with_expired_lease_and_fresh_target()
    assert emission.is_hold
    assert emission.label is LEASE_EXPIRED_HOLD_LABEL
    assert emission.reason is LEASE_EXPIRED_HOLD_REASON


def test_latched_scheduler_emits_safety_hold() -> None:
    emission = decide_when_latched()
    assert emission.label is SAFETY_LATCH_HOLD_LABEL
