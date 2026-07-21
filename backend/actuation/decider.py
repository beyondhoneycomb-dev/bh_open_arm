"""The four-emission decider — a total priority order over one tick's state.

This is the single function that answers "what does this tick emit?", and it is
written as a strict `if / elif / … / else` chain for one reason: a total order
returns **exactly one** emission by construction. Zero is impossible because the
chain ends in an unconditional `else`; two is impossible because control leaves at
the first matching branch. Acceptance ① (a million ticks, never zero, never two)
is therefore a property of the shape of this function, which the scheduler then
re-checks at runtime against the actual CAN write count.

The priority, highest first, and why each sits where it does:

1. **Safety latch.** A latched hold overrides everything and persists until an
   operator ack (`12` FR-SAF-074 ⑤). Nothing a producer does can lift it.
2. **Lease expiry.** The deadman lapsing is a safety event (`04` FR-MAN-050), and
   acceptance ④ requires its decision to be independent of producer state — so it
   is evaluated before any producer/mailbox condition, above even a mode
   transition. A fresh target does not keep a lapsed deadman live.
3. **Mode transition.** While a producer swap is bracketed, the scheduler holds
   rather than read a producer being wound down (`02a` §3.1 ④).
4. **Stale / empty mailbox.** No source, or a source older than the freshness
   window, is a STALE_SOURCE_HOLD (`02a` §3.1 ③).
5. **Accepted target.** Only when none of the above holds: the fresh request is
   clamped, crossed to radians, and emitted.

Every branch produces a full MIT batch. A hold batch holds the last accepted
positions; the accepted branch commands the freshly clamped ones. Same shape,
different angles — the arm is always commanded, never cut.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation.emissions import Emission, EmissionLabel, ReasonCode
from backend.actuation.gateway import (
    JointLimit,
    accepted_to_rad,
    clamp_request,
    positions_to_batch,
)
from backend.actuation.mailbox import TimestampedTarget
from contracts.action import ExecutedMitCommand


@dataclass(frozen=True)
class DeciderInput:
    """One tick's decision inputs, snapshotted so the decider stays pure.

    The hold frame is passed in pre-built rather than reconstructed here: a hold is
    the *same* MIT position-hold frame re-sent (`02a` §3.1 ⑤), so the scheduler
    caches it and only rebuilds it when a fresh accepted target moves the hold
    point. That keeps a held tick allocation-free, which is what lets the
    million-tick invariant run (acceptance ①) stay fast.

    Attributes:
        now: Current clock reading, in seconds.
        safety_latched: Whether the safety latch is held.
        transition_in_progress: Whether a producer swap is bracketed.
        lease_expired: Whether the deadman lease has lapsed as of `now`.
        mailbox_target: The freshest published target, or None.
        hold_batch: The MIT frame a hold re-sends — the last accepted command.
        freshness_window_sec: Age past which a mailbox target is stale.
        joint_limits: Per-joint clamp bounds, or None to clamp no joint.
    """

    now: float
    safety_latched: bool
    transition_in_progress: bool
    lease_expired: bool
    mailbox_target: TimestampedTarget | None
    hold_batch: tuple[ExecutedMitCommand, ...]
    freshness_window_sec: float
    joint_limits: tuple[JointLimit | None, ...] | None


def decide(state: DeciderInput) -> Emission:
    """Return the single emission this tick's state warrants.

    Args:
        state: The tick's snapshotted decision inputs.

    Returns:
        (Emission) Exactly one emission — one of the four labels, its reason code,
        and the full MIT batch to write.
    """
    if state.safety_latched:
        return Emission(EmissionLabel.SAFETY_LATCH_HOLD, ReasonCode.SAFETY_LATCH, state.hold_batch)

    if state.lease_expired:
        return Emission(EmissionLabel.STALE_SOURCE_HOLD, ReasonCode.LEASE_EXPIRED, state.hold_batch)

    if state.transition_in_progress:
        return Emission(
            EmissionLabel.MODE_TRANSITION_HOLD, ReasonCode.PRODUCER_SWAP, state.hold_batch
        )

    if state.mailbox_target is None:
        return Emission(EmissionLabel.STALE_SOURCE_HOLD, ReasonCode.MAILBOX_EMPTY, state.hold_batch)

    age = state.now - state.mailbox_target.published_at
    if age > state.freshness_window_sec:
        return Emission(EmissionLabel.STALE_SOURCE_HOLD, ReasonCode.MAILBOX_STALE, state.hold_batch)

    accepted, _override = clamp_request(state.mailbox_target.request, state.joint_limits)
    accepted_batch = positions_to_batch(accepted_to_rad(accepted))
    return Emission(EmissionLabel.ACCEPTED_TARGET, ReasonCode.FRESH, accepted_batch)
