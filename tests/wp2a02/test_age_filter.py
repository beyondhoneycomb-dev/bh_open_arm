"""Acceptance ④ — a renewal delayed past max_lease_age is discarded, not honoured late.

A renewal that was issued in order but sat in the network longer than `max_lease_age`
is invalid, not "valid but late": honouring it would extend a lease that should have
lapsed, which is how a delayed packet turns into an arm that stops and then moves on
its own. The age is measured on the server clock against the client's issue time
mapped into the server frame, so the client cannot argue its way out of it.
"""

from __future__ import annotations

from backend.deadman import LeaseRenewal, RenewalDecision, RenewalReceiver
from tests.wp2a02.conftest import DeadmanHarness

_LEASE_DURATION_SEC = 0.1
_MAX_LEASE_AGE_SEC = 0.05


def _receiver() -> RenewalReceiver:
    """Build an armed receiver at the bench durations."""
    receiver = RenewalReceiver(_LEASE_DURATION_SEC, _MAX_LEASE_AGE_SEC)
    receiver.arm(0)
    return receiver


def test_first_renewal_of_a_generation_sets_the_age_baseline() -> None:
    """The first renewal establishes the offset and cannot be discarded for age (④)."""
    receiver = _receiver()
    # Issued and received with a large clock skew: age is zero by definition here
    # because this message defines the alignment, so skew does not discard it.
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=1000.0),
        server_received_at=5.0,
        latched=False,
    )
    assert result.accepted
    assert result.lease is not None
    # Expiry is stamped on the server clock, not the client clock.
    assert result.lease.expiry_mono_server == 5.0 + _LEASE_DURATION_SEC


def test_delayed_renewal_over_max_age_is_discarded() -> None:
    """A fresh-sequence renewal aged past the bound is discarded (④)."""
    receiver = _receiver()
    receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=10.0),
        server_received_at=10.0,
        latched=False,
    )
    # Issued 0.06 s ago (age 0.06 > 0.05), fresh sequence: delayed in transit.
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=2, issued_mono_client=10.54),
        server_received_at=10.60,
        latched=False,
    )
    assert result.decision is RenewalDecision.DISCARDED_AGED
    assert result.lease is None


def test_discard_does_not_consume_the_sequence() -> None:
    """A discarded renewal does not advance anti-replay, so a fresh one still lands (④)."""
    receiver = _receiver()
    receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=10.0),
        server_received_at=10.0,
        latched=False,
    )
    discarded = receiver.receive(
        LeaseRenewal(generation=0, sequence=2, issued_mono_client=10.54),
        server_received_at=10.60,
        latched=False,
    )
    assert discarded.decision is RenewalDecision.DISCARDED_AGED
    # A later, on-time renewal with a higher sequence is accepted — the discard left
    # no trace in the anti-replay state.
    accepted = receiver.receive(
        LeaseRenewal(generation=0, sequence=3, issued_mono_client=10.61),
        server_received_at=10.61,
        latched=False,
    )
    assert accepted.accepted


def test_on_time_renewal_just_under_the_bound_is_accepted() -> None:
    """A renewal aged just under max_lease_age is still valid (④ boundary)."""
    receiver = _receiver()
    receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=0.0),
        server_received_at=0.0,
        latched=False,
    )
    # Age 0.04 < 0.05.
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=2, issued_mono_client=1.0),
        server_received_at=1.04,
        latched=False,
    )
    assert result.accepted


def test_delayed_renewal_does_not_extend_the_lease_on_the_spine() -> None:
    """On the real spine, a discarded renewal does not push out the expiry (④)."""
    harness = DeadmanHarness(
        lease_duration_sec=_LEASE_DURATION_SEC, max_lease_age_sec=_MAX_LEASE_AGE_SEC
    )
    harness.take_deadman()
    # Renew on time a few ticks; record the server time of the last good renewal.
    for _ in range(5):
        harness.tick(publish=True, renew=True)
    last_good_renewal_at = harness.clock.now()

    # A renewal issued well over max_lease_age ago arrives now — it is discarded and
    # must not extend the lease past the last good renewal's horizon.
    harness.advance()
    stale_issue_time = harness.clock.now() - (_MAX_LEASE_AGE_SEC + 0.02)
    result = harness.renew(issued_mono_client=stale_issue_time)
    assert result.decision is RenewalDecision.DISCARDED_AGED

    # The lease still expires at the last good renewal + duration, not at the
    # discarded renewal's arrival + duration.
    just_after_true_expiry = last_good_renewal_at + _LEASE_DURATION_SEC + 1e-6
    assert harness.lease.is_expired(just_after_true_expiry)
