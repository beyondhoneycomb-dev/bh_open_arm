"""The deadman lease wire message, the server-held lease record, and renewal outcomes.

Two types, and the split between them is the load-bearing decision of this WP:

- `LeaseRenewal` is what a client sends. It carries `generation`, `sequence`, and
  `issued_mono_client` — and deliberately **no expiry**. A client cannot state when
  its own lease expires; that is the server's alone (U-4 clock ownership).
- `DeadmanLease` is what the server holds after accepting a renewal. It adds
  `expiry_mono_server`, computed on the server's own monotonic clock. This is the
  named deliverable `DeadmanLease{generation, expiry_mono_server, sequence,
  issued_mono_client}` (`02b` §1.2).

Keeping expiry out of the wire message is what makes acceptance ⑥ structural: the
expiry field simply does not exist on anything a client authored, so no expiry
decision can read a client-supplied time by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class LeaseRenewal:
    """A client-authored renewal message: "I am still here", with anti-replay metadata.

    Ownership of each field's clock is the point: `issued_mono_client` is the
    client's monotonic reading and is used **only** as an age input (mapped into the
    server frame by `ClientClockOffset`), never as an expiry input. The wire message
    carries no expiry, so a client has no path to claim its lease is still live.

    Attributes:
        generation: The re-arm epoch this renewal belongs to. A client may only send
            the generation the server issued to it; a client cannot mint a new one.
        sequence: Strictly increasing per-generation counter, for anti-replay. A
            sequence at or below the last accepted one is a replay or a reorder.
        issued_mono_client: The client's monotonic clock reading when it issued this
            renewal, in seconds. An age input only — never an expiry input.
    """

    generation: int
    sequence: int
    issued_mono_client: float


@dataclass(frozen=True)
class DeadmanLease:
    """The server-held lease record after a renewal is accepted (the WP deliverable).

    `expiry_mono_server` is computed on the server clock at acceptance and is the
    sole authority on when this lease expires. `issued_mono_client` is retained for
    the audit and as the age baseline for the next renewal, but nothing derives
    expiry from it.

    Attributes:
        generation: The re-arm epoch the accepted renewal belonged to.
        expiry_mono_server: Server-clock time at which this lease expires, in
            seconds. Server-authored; the only expiry authority (U-4).
        sequence: The sequence number of the renewal that established this lease.
        issued_mono_client: The client's issue time of that renewal, kept for audit
            and as the next age baseline — not for expiry.
    """

    generation: int
    expiry_mono_server: float
    sequence: int
    issued_mono_client: float


class RenewalDecision(Enum):
    """Why the receiver accepted or refused a renewal.

    One reason per refusal rather than a single "rejected": the audit must tell a
    replay from an aged message from a latched refusal, because they mean different
    things about the operator and the link (`02b` §1.2 negative branch).
    """

    ACCEPTED = "accepted"
    # The deadman has latched (expiry, no auto-resume). Only a re-arm handshake
    # resumes; no renewal for any existing generation is accepted while latched.
    REJECTED_LATCHED = "rejected_latched"
    # No generation is armed yet (before the first take of the deadman).
    REJECTED_UNARMED = "rejected_unarmed"
    # A generation older than the armed one — a stale, pre-re-arm renewal.
    REJECTED_STALE_GENERATION = "rejected_stale_generation"
    # A generation newer than the armed one — a client cannot mint generations.
    REJECTED_UNKNOWN_GENERATION = "rejected_unknown_generation"
    # Sequence at or below the last accepted — a replay or a reorder (anti-replay).
    REJECTED_REPLAY = "rejected_replay"
    # Age over `max_lease_age` — issued in order but delayed in transit; invalid.
    DISCARDED_AGED = "discarded_aged"


@dataclass(frozen=True)
class RenewalResult:
    """The receiver's verdict on one renewal, and the lease it produced if accepted.

    Attributes:
        decision: The single reason the renewal was accepted or refused.
        lease: The server-held lease built on acceptance, or None on any refusal.
    """

    decision: RenewalDecision
    lease: DeadmanLease | None = None

    @property
    def accepted(self) -> bool:
        """Whether the renewal was accepted and extended the lease.

        Returns:
            (bool) True only for an accepted renewal.
        """
        return self.decision is RenewalDecision.ACCEPTED
