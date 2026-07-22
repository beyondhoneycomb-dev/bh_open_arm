"""Acceptance ⑩ / ⑪ / ⑫ — fail-closed detection, paused in bus-exclusive, latched until ack.

The collision guard detects; it never writes the bus (`12` FR-SAF-074 ③). It sets the
safety latch and the scheduler holds. What is checked here:

- ⑩ A blind guard latches immediately on any of three conditions — a missing
  observation, a failed bus read, a lock timeout — each with its own distinct cause.
- ⑪ During a bus-exclusive section (torque enable, mode set) the guard is paused, so
  the torn read those sections produce raises no false latch.
- ⑫ Once latched, nothing in the tick path clears it: only an operator acknowledge
  releases the latch, and the cause is recorded in the latch reason.
"""

from __future__ import annotations

from backend.actuation import (
    CollisionGuard,
    GuardCause,
    GuardSample,
    ManualClock,
    SafetyLatch,
)
from ops.cancel.scheduler import LatchReason


def _guard_with_latch() -> tuple[CollisionGuard, SafetyLatch]:
    """Build a guard whose latch callback engages a real one-way `SafetyLatch`."""
    latch = SafetyLatch()
    guard = CollisionGuard(on_latch=latch.engage, clock=ManualClock())
    return guard, latch


def test_three_fail_closed_conditions_each_latch_immediately() -> None:
    """Missing obs, bus-read fail, and lock timeout each latch with a distinct cause (⑩)."""
    conditions = {
        GuardCause.OBSERVATION_MISSING: GuardSample(
            observation_present=False, bus_read_ok=True, lock_acquired=True, residual_exceeded=False
        ),
        GuardCause.BUS_READ_FAILED: GuardSample(
            observation_present=True, bus_read_ok=False, lock_acquired=True, residual_exceeded=False
        ),
        GuardCause.LOCK_TIMEOUT: GuardSample(
            observation_present=True, bus_read_ok=True, lock_acquired=False, residual_exceeded=False
        ),
    }
    for expected_cause, sample in conditions.items():
        guard, latch = _guard_with_latch()
        verdict = guard.poll(sample)
        assert verdict.latched
        assert verdict.cause is expected_cause
        assert guard.is_latched
        assert latch.is_active


def test_healthy_poll_does_not_latch() -> None:
    """A poll with everything nominal latches nothing (⑩, no over-eager latch)."""
    guard, latch = _guard_with_latch()
    verdict = guard.poll(GuardSample.healthy())
    assert not verdict.latched
    assert not latch.is_active


def test_paused_guard_raises_no_false_latch_in_bus_exclusive_section() -> None:
    """Paused for a bus-exclusive section, a fail-closed sample raises no latch (⑪)."""
    guard, latch = _guard_with_latch()
    guard.pause()
    blind = GuardSample(
        observation_present=False, bus_read_ok=False, lock_acquired=False, residual_exceeded=True
    )
    verdict = guard.poll(blind)
    assert not verdict.latched
    assert not latch.is_active
    # After the section ends, the same blind sample latches — pausing suppressed
    # nothing permanently, it only covered the exclusive window.
    guard.resume()
    assert guard.poll(blind).latched
    assert latch.is_active


def test_latch_holds_until_operator_ack_and_records_cause() -> None:
    """A latch never self-clears; only an ack releases it, and the cause is recorded (⑫)."""
    guard, latch = _guard_with_latch()
    guard.poll(
        GuardSample(
            observation_present=False, bus_read_ok=True, lock_acquired=True, residual_exceeded=False
        )
    )
    assert latch.is_active
    cause: LatchReason | None = latch.reason
    assert cause is not None
    assert GuardCause.OBSERVATION_MISSING.value in cause.gate_id

    # Further healthy polls do not release the latch — there is no self-clear path.
    for _ in range(5):
        guard.poll(GuardSample.healthy())
    assert latch.is_active
    assert not hasattr(latch, "release")

    # Only the operator acknowledge clears it.
    latch.acknowledge()
    assert not latch.is_active


def test_residual_collision_debounces_before_latching() -> None:
    """A one-off residual does not latch; a sustained one does (debounced collision)."""
    guard, latch = _guard_with_latch()
    residual = GuardSample(
        observation_present=True, bus_read_ok=True, lock_acquired=True, residual_exceeded=True
    )
    # One over-threshold poll below the debounce count does not latch.
    assert not guard.poll(residual).latched
    assert not guard.poll(residual).latched
    # The third consecutive one crosses the default debounce and latches.
    assert guard.poll(residual).latched
    assert latch.is_active
