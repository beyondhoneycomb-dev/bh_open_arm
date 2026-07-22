"""The server clock owns expiry; the client clock only feeds age.

`02b` §1.2: the expiry-deciding monotonic clock is the server's, and the client clock
is an age input that never touches the expiry decision. If a client could keep its
lease alive by its own clock, it would own the deadman. These tests show the produced
lease's expiry is stamped from the server receive time, and that a wildly-skewed
client clock changes nothing about when the lease lapses on the spine.
"""

from __future__ import annotations

from backend.deadman import LeaseRenewal, RenewalReceiver
from tests.wp2a02.conftest import (
    LEASE_DURATION_SEC,
    TICK_INTERVAL_SEC,
    DeadmanHarness,
)

_MAX_LEASE_AGE_SEC = 0.05
_DURATION_TICKS = round(LEASE_DURATION_SEC / TICK_INTERVAL_SEC)
_EXPIRY_CEILING_TICKS = 200


def test_expiry_is_stamped_from_the_server_receive_time() -> None:
    """The accepted lease's expiry is server_received_at + duration, not client-derived."""
    receiver = RenewalReceiver(LEASE_DURATION_SEC, _MAX_LEASE_AGE_SEC)
    receiver.arm(0)
    # A client issue time far from the server time; expiry must ignore it.
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=9_999.0),
        server_received_at=3.0,
        latched=False,
    )
    assert result.lease is not None
    assert result.lease.expiry_mono_server == 3.0 + LEASE_DURATION_SEC
    # The client's issue time is retained only for audit and the next age baseline.
    assert result.lease.issued_mono_client == 9_999.0


def test_skewed_client_clock_does_not_change_when_the_lease_lapses() -> None:
    """A large client skew leaves the expiry tick governed purely by the server clock."""
    aligned = DeadmanHarness(max_lease_age_sec=LEASE_DURATION_SEC)
    skewed = DeadmanHarness(max_lease_age_sec=LEASE_DURATION_SEC, client_skew_sec=10_000.0)

    aligned.take_deadman()
    skewed.take_deadman()

    aligned_latch = aligned.run_until_latched(_EXPIRY_CEILING_TICKS)
    skewed_latch = skewed.run_until_latched(_EXPIRY_CEILING_TICKS)

    # Both latch at the same server-clock offset; the client skew does not defer it.
    assert aligned_latch == skewed_latch


def test_client_cannot_defer_expiry_by_claiming_a_future_issue_time() -> None:
    """A renewal claiming a future client time cannot push the server-clock expiry out.

    The wire message carries no expiry, so a client's only lever is `issued_mono_client`
    — and that reaches age only. Once the server clock passes the lease horizon, the
    lease is expired no matter what issue time the last renewal claimed.
    """
    harness = DeadmanHarness(max_lease_age_sec=LEASE_DURATION_SEC)
    harness.take_deadman()
    # Renew with an absurd future client issue time; it is still accepted (age is
    # measured against the established offset, and the first message set that offset).
    harness.advance()
    harness.renew(issued_mono_client=harness.clock.now() + 1_000_000.0)
    renew_server_time = harness.clock.now()

    # The server clock, advanced past the horizon, expires the lease regardless.
    assert harness.lease.is_expired(renew_server_time + LEASE_DURATION_SEC + 1e-6)
