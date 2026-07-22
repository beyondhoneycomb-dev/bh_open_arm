"""Anti-replay and generation gate — sequence regression/dup and forged generations.

`02b` §1.2: sequence regression or duplication is an anti-replay reject, and a client
may only renew under the generation the server issued to it. These are the checks that
stop a captured renewal from being replayed, and stop a client from asserting a newer
generation to talk itself back to a live arm after a latch — generations are minted by
the server's re-arm handshake alone.
"""

from __future__ import annotations

from backend.deadman import LeaseRenewal, RenewalDecision, RenewalReceiver

_LEASE_DURATION_SEC = 0.1
_MAX_LEASE_AGE_SEC = 0.05


def _armed_receiver_with_one_accepted() -> RenewalReceiver:
    """An armed receiver that has accepted sequence 1 of generation 0."""
    receiver = RenewalReceiver(_LEASE_DURATION_SEC, _MAX_LEASE_AGE_SEC)
    receiver.arm(0)
    receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=0.0),
        server_received_at=0.0,
        latched=False,
    )
    return receiver


def test_sequence_regression_is_rejected() -> None:
    """A renewal with a sequence below the last accepted is a replay reject."""
    receiver = _armed_receiver_with_one_accepted()
    receiver.receive(
        LeaseRenewal(generation=0, sequence=5, issued_mono_client=0.01),
        server_received_at=0.01,
        latched=False,
    )
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=4, issued_mono_client=0.02),
        server_received_at=0.02,
        latched=False,
    )
    assert result.decision is RenewalDecision.REJECTED_REPLAY


def test_duplicate_sequence_is_rejected() -> None:
    """A renewal repeating the last accepted sequence is a replay reject."""
    receiver = _armed_receiver_with_one_accepted()
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=0.01),
        server_received_at=0.01,
        latched=False,
    )
    assert result.decision is RenewalDecision.REJECTED_REPLAY


def test_strictly_increasing_sequences_are_accepted() -> None:
    """Monotonically increasing sequences pass anti-replay."""
    receiver = _armed_receiver_with_one_accepted()
    for sequence in (2, 3, 10):
        result = receiver.receive(
            LeaseRenewal(generation=0, sequence=sequence, issued_mono_client=0.0),
            server_received_at=0.0,
            latched=False,
        )
        assert result.accepted


def test_older_generation_is_rejected_as_stale() -> None:
    """A renewal under a generation below the armed one is a stale-generation reject."""
    receiver = RenewalReceiver(_LEASE_DURATION_SEC, _MAX_LEASE_AGE_SEC)
    receiver.arm(2)
    result = receiver.receive(
        LeaseRenewal(generation=1, sequence=1, issued_mono_client=0.0),
        server_received_at=0.0,
        latched=False,
    )
    assert result.decision is RenewalDecision.REJECTED_STALE_GENERATION


def test_newer_generation_is_rejected_as_unknown() -> None:
    """A client cannot mint a newer generation to renew under — it is refused."""
    receiver = RenewalReceiver(_LEASE_DURATION_SEC, _MAX_LEASE_AGE_SEC)
    receiver.arm(0)
    result = receiver.receive(
        LeaseRenewal(generation=1, sequence=1, issued_mono_client=0.0),
        server_received_at=0.0,
        latched=False,
    )
    assert result.decision is RenewalDecision.REJECTED_UNKNOWN_GENERATION


def test_renewal_before_any_arm_is_rejected() -> None:
    """A renewal with no generation armed yet is refused."""
    receiver = RenewalReceiver(_LEASE_DURATION_SEC, _MAX_LEASE_AGE_SEC)
    result = receiver.receive(
        LeaseRenewal(generation=0, sequence=1, issued_mono_client=0.0),
        server_received_at=0.0,
        latched=False,
    )
    assert result.decision is RenewalDecision.REJECTED_UNARMED
