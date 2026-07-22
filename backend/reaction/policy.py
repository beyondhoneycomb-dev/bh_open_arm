"""The reaction latch policy — `latch_until_ack=true`, `auto_resume=false`, frozen.

`FR-SAF-043` fixes the two latch defaults and they are not tunable: a protection stop
must not auto-resume (ISO 10218), so a policy that sets `auto_resume=true` or
`latch_until_ack=false` is refused at construction rather than accepted and quietly
defeating the latch. The policy carries the selected strategy alongside the flags, so
"which reaction, latched how" is one value.

The policy does not *hold* the latch — the latch is the Wave-1 scheduler's one-way
`SafetyLatch` (`backend.actuation`), reused so there is a single latch implementation
for both a cancellation and a collision reaction (`executor` engages it). This module
only fixes the policy the executor enforces.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.reaction.constants import AUTO_RESUME_DEFAULT, LATCH_UNTIL_ACK_DEFAULT
from backend.reaction.strategy import DEFAULT_STRATEGY, ReactionStrategy


class ReactionPolicyError(ValueError):
    """Raised when a policy would defeat the `FR-SAF-043` latch (auto-resume / no latch)."""


@dataclass(frozen=True)
class ReactionPolicy:
    """The reaction strategy and its latch behaviour (`FR-SAF-037`, `FR-SAF-043`).

    Attributes:
        strategy: The reaction applied on a confirmed collision; defaults to STOP_HOLD.
        latch_until_ack: Must stay True — the reaction latches until an operator
            acknowledges (`FR-SAF-043`).
        auto_resume: Must stay False — a protection stop never auto-resumes
            (`FR-SAF-043`).
    """

    strategy: ReactionStrategy = DEFAULT_STRATEGY
    latch_until_ack: bool = LATCH_UNTIL_ACK_DEFAULT
    auto_resume: bool = AUTO_RESUME_DEFAULT

    def __post_init__(self) -> None:
        """Refuse a policy that would let motion resume without an operator ack.

        Raises:
            ReactionPolicyError: If `latch_until_ack` is False or `auto_resume` is True.
        """
        if not self.latch_until_ack:
            raise ReactionPolicyError(
                "latch_until_ack must be True: a collision reaction latches until an operator "
                "acknowledges it (FR-SAF-043)"
            )
        if self.auto_resume:
            raise ReactionPolicyError(
                "auto_resume must be False: a protection stop never auto-resumes (FR-SAF-043, "
                "ISO 10218)"
            )
