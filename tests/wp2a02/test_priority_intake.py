"""Acceptance ⑧ — renewals are never delayed or dropped behind bulk (camera) frames.

`02b` §1.0 requires the lease renewal stream to be the highest-priority class so a
flood of camera frames cannot delay it (the head-of-line hazard of the single WS).
The production mitigation is the WS transport frozen as `CTR-WS@v1` (`WP-3A-04`); this
exercises the deadman-side intake that models the invariant: renewals drain ahead of
bulk and survive a bulk flood that sheds only bulk.
"""

from __future__ import annotations

from backend.deadman import IntakeClass, RenewalIntake

_RENEWAL_CAPACITY = 64
_BULK_CAPACITY = 8


def _intake() -> RenewalIntake[str]:
    """A string-payload intake at the bench capacities."""
    return RenewalIntake(renewal_capacity=_RENEWAL_CAPACITY, bulk_capacity=_BULK_CAPACITY)


def test_renewals_drain_before_bulk_even_when_offered_after() -> None:
    """Every renewal drains ahead of every bulk item, regardless of arrival order (⑧)."""
    intake = _intake()
    intake.offer("bulk-0", IntakeClass.BULK)
    intake.offer("renew-0", IntakeClass.RENEWAL)
    intake.offer("bulk-1", IntakeClass.BULK)
    intake.offer("renew-1", IntakeClass.RENEWAL)

    drained = intake.drain()
    assert drained == ["renew-0", "renew-1", "bulk-0", "bulk-1"]


def test_bulk_flood_never_drops_or_delays_a_renewal() -> None:
    """A bulk flood past its bound sheds only bulk; every renewal survives, drains first (⑧)."""
    intake = _intake()
    # Interleave a modest renewal stream with a bulk flood far exceeding the bulk bound.
    renewals = [f"renew-{i}" for i in range(20)]
    for i in range(200):
        intake.offer(f"bulk-{i}", IntakeClass.BULK)
        if i < len(renewals):
            intake.offer(renewals[i], IntakeClass.RENEWAL)

    assert intake.bulk_dropped > 0  # the flood did shed bulk
    assert intake.renewal_overflowed == 0  # but never a renewal

    drained = intake.drain()
    surviving_renewals = [item for item in drained if item.startswith("renew-")]
    assert surviving_renewals == renewals  # all present, in order
    # And every renewal precedes every bulk item in the drained order.
    first_bulk_index = next(i for i, item in enumerate(drained) if item.startswith("bulk-"))
    assert all(item.startswith("renew-") for item in drained[:first_bulk_index])


def test_bulk_sheds_its_oldest_under_pressure() -> None:
    """The bulk class keeps only its most recent items, dropping the oldest (⑧)."""
    intake = _intake()
    for i in range(_BULK_CAPACITY + 3):
        intake.offer(f"bulk-{i}", IntakeClass.BULK)

    drained = intake.drain()
    assert intake.bulk_dropped == 3
    # The three oldest were shed; the newest bulk_capacity remain, in order.
    assert drained == [f"bulk-{i}" for i in range(3, _BULK_CAPACITY + 3)]


def test_renewal_overflow_is_reported_not_silent() -> None:
    """Filling the renewal class refuses the extra and counts it, never dropping silently (⑧)."""
    intake = RenewalIntake[str](renewal_capacity=2, bulk_capacity=4)
    assert intake.offer("r0", IntakeClass.RENEWAL) is True
    assert intake.offer("r1", IntakeClass.RENEWAL) is True
    # The third renewal cannot be admitted; it is refused (False) and counted, so the
    # caller can treat renewals arriving faster than they drain as a fault.
    assert intake.offer("r2", IntakeClass.RENEWAL) is False
    assert intake.renewal_overflowed == 1
    # The buffered renewals are the first two — the newest was refused, not swapped in.
    assert intake.drain() == ["r0", "r1"]
