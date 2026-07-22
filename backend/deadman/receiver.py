"""The renewal receiver — anti-replay, generation gate, and age filter over one renewal.

This is the pure decision half of the deadman: given a `LeaseRenewal`, the server's
receive time, and whether the deadman is latched, it returns one `RenewalResult`.
It holds the anti-replay and generation state and delegates every client-clock read
to `ClientClockOffset`, so it can be tested in isolation and so nothing here touches
the expiry decision.

It does **not** hold the `LeaseManager` or the latch. Renewing the reused lease and
reading the reused latch belong to `DeadmanController`, which owns the integration;
keeping them out of here is what lets the receiver be a total function of its inputs.
"""

from __future__ import annotations

from backend.deadman.age_filter import ClientClockOffset
from backend.deadman.messages import (
    DeadmanLease,
    LeaseRenewal,
    RenewalDecision,
    RenewalResult,
)


class RenewalReceiver:
    """Judges a renewal against the armed generation, the last sequence, and its age.

    State: the armed generation, the highest accepted sequence within it, and the
    client-clock offset for it. `arm` (re)sets all three for a new generation; every
    other method is a read or a judgement.
    """

    def __init__(self, lease_duration_sec: float, max_lease_age_sec: float) -> None:
        """Create a receiver with no generation armed.

        Args:
            lease_duration_sec: How far past the server receive time an accepted
                renewal sets the lease expiry — the server-clock expiry horizon.
            max_lease_age_sec: Age past which an arrived renewal is discarded.
        """
        self._lease_duration_sec = lease_duration_sec
        self._max_lease_age_sec = max_lease_age_sec
        self._armed_generation: int | None = None
        self._last_sequence: int | None = None
        self._offset = ClientClockOffset()

    @property
    def armed_generation(self) -> int | None:
        """The generation currently accepted, or None before the first arm.

        Returns:
            (int | None) The armed generation.
        """
        return self._armed_generation

    def arm(self, generation: int) -> None:
        """Accept renewals for `generation`, resetting anti-replay and the age baseline.

        The sequence counter and the client-clock offset are per-generation: a new
        generation starts its own anti-replay history and re-estimates the offset
        from its first renewal (`02b` §1.0: re-estimation only on a new generation).

        Args:
            generation: The generation to accept renewals for.
        """
        self._armed_generation = generation
        self._last_sequence = None
        self._offset.reset()

    def receive(
        self, renewal: LeaseRenewal, server_received_at: float, latched: bool
    ) -> RenewalResult:
        """Judge one renewal and, on acceptance, build the server-held lease.

        The checks run in a fixed order so each refusal has one unambiguous reason:
        latched first (a latched deadman accepts nothing), then armed-ness, then the
        generation gate, then anti-replay, then the age filter. Anti-replay precedes
        the age filter on purpose — a replay carries a stale sequence, whereas a
        delayed-but-in-order renewal carries a fresh one, so testing sequence first
        keeps the two failures distinct.

        Args:
            renewal: The client-authored renewal to judge.
            server_received_at: The server clock reading at receipt, in seconds. The
                sole time base for the produced lease's expiry.
            latched: Whether the deadman is currently latched. When True, the renewal
                is refused regardless of its contents — resume takes a re-arm, never
                a renewal (U-4, acceptance ③).

        Returns:
            (RenewalResult) The single decision, plus the lease when accepted.
        """
        if latched:
            return RenewalResult(RenewalDecision.REJECTED_LATCHED)

        if self._armed_generation is None:
            return RenewalResult(RenewalDecision.REJECTED_UNARMED)

        if renewal.generation != self._armed_generation:
            if renewal.generation < self._armed_generation:
                return RenewalResult(RenewalDecision.REJECTED_STALE_GENERATION)
            return RenewalResult(RenewalDecision.REJECTED_UNKNOWN_GENERATION)

        if self._last_sequence is not None and renewal.sequence <= self._last_sequence:
            return RenewalResult(RenewalDecision.REJECTED_REPLAY)

        if not self._offset.is_estimated:
            # The first renewal of the generation defines the client/server
            # alignment; its own age is zero and it cannot be discarded for age.
            self._offset.estimate(renewal.issued_mono_client, server_received_at)
        elif (
            self._offset.age(renewal.issued_mono_client, server_received_at)
            > self._max_lease_age_sec
        ):
            # Delayed in transit past the age bound: discard without advancing the
            # sequence, so it neither extends the lease nor counts as "seen".
            return RenewalResult(RenewalDecision.DISCARDED_AGED)

        self._last_sequence = renewal.sequence
        lease = DeadmanLease(
            generation=renewal.generation,
            expiry_mono_server=server_received_at + self._lease_duration_sec,
            sequence=renewal.sequence,
            issued_mono_client=renewal.issued_mono_client,
        )
        return RenewalResult(RenewalDecision.ACCEPTED, lease)
