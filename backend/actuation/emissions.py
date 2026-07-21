"""The four emission labels and their reason codes — the alphabet of every tick.

The interface contract (`02a` §3.1 ③) fixes exactly four emission labels, and the
invariant is that a tick emits **exactly one** of them: zero is a violation the
scheduler asserts against, and two is impossible because the decider is a total
priority order (`backend.actuation.decider`).

A label is the coarse kind of frame the tick wrote; a reason code is the finer
"why". They are separated because acceptance ⑨ requires the trace to carry both,
and because one label legitimately arises from several distinct causes — a
STALE_SOURCE_HOLD is emitted both when the mailbox has gone stale and when the
deadman lease has expired, and an audit that could not tell those two apart would
be unable to attribute a drop to the operator versus to the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from contracts.action import ExecutedMitCommand


class EmissionLabel(Enum):
    """The four — and only four — things a tick may emit (`02a` §3.1 ③)."""

    ACCEPTED_TARGET = "ACCEPTED_TARGET"
    STALE_SOURCE_HOLD = "STALE_SOURCE_HOLD"
    MODE_TRANSITION_HOLD = "MODE_TRANSITION_HOLD"
    SAFETY_LATCH_HOLD = "SAFETY_LATCH_HOLD"


# The three hold labels. ACCEPTED_TARGET is the only non-hold emission, so a hold
# is "any label that is not ACCEPTED_TARGET"; naming the set keeps that definition
# in one place rather than scattering `!= ACCEPTED_TARGET` across call sites.
HOLD_LABELS = frozenset(
    {
        EmissionLabel.STALE_SOURCE_HOLD,
        EmissionLabel.MODE_TRANSITION_HOLD,
        EmissionLabel.SAFETY_LATCH_HOLD,
    }
)


class ReasonCode(Enum):
    """Why a tick emitted the label it did (the finer axis acceptance ⑨ records)."""

    # ACCEPTED_TARGET
    FRESH = "fresh"
    # STALE_SOURCE_HOLD
    MAILBOX_EMPTY = "mailbox_empty"
    MAILBOX_STALE = "mailbox_stale"
    LEASE_EXPIRED = "lease_expired"
    # MODE_TRANSITION_HOLD
    PRODUCER_SWAP = "producer_swap"
    # SAFETY_LATCH_HOLD
    SAFETY_LATCH = "safety_latch"


@dataclass(frozen=True)
class Emission:
    """The single decision a tick reached, before it was written to CAN.

    The decider produces one of these per tick and nothing else; the scheduler
    turns it into exactly one MIT batch. Carrying the batch here (rather than
    rebuilding it downstream) keeps the emitted frame and the audit record the
    same object, so the audit channel (`02a` §3.1 ⑥) cannot drift from what was
    actually sent.

    Attributes:
        label: Which of the four emission kinds this tick is.
        reason: The finer cause, recorded alongside the label for the trace.
        batch: The 16 per-joint MIT commands written to CAN this tick. A hold and
            an accepted target both carry a full batch; they differ in the target
            position, not in shape.
    """

    label: EmissionLabel
    reason: ReasonCode
    batch: tuple[ExecutedMitCommand, ...]

    @property
    def is_hold(self) -> bool:
        """Whether this emission is one of the three hold labels.

        Returns:
            (bool) True unless the label is ACCEPTED_TARGET.
        """
        return self.label in HOLD_LABELS
