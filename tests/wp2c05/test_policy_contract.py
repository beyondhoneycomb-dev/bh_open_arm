"""The reaction policy freezes `latch_until_ack=true` / `auto_resume=false` (`FR-SAF-043`).

The two latch defaults are not tunable: a policy that would let a protection stop
auto-resume, or not latch at all, is refused at construction rather than accepted and
quietly defeating the latch (ISO 10218: no auto-resume after a protection stop).
"""

from __future__ import annotations

import pytest

from backend.reaction import ReactionPolicy, ReactionPolicyError, ReactionStrategy


def test_default_policy_is_stop_hold_latched_no_resume() -> None:
    """The default policy is STOP_HOLD, latched until ack, no auto-resume."""
    policy = ReactionPolicy()
    assert policy.strategy is ReactionStrategy.STOP_HOLD
    assert policy.latch_until_ack is True
    assert policy.auto_resume is False


def test_auto_resume_true_is_refused() -> None:
    """A policy with `auto_resume=True` is refused (`FR-SAF-043`)."""
    with pytest.raises(ReactionPolicyError):
        ReactionPolicy(auto_resume=True)


def test_latch_until_ack_false_is_refused() -> None:
    """A policy with `latch_until_ack=False` is refused (`FR-SAF-043`)."""
    with pytest.raises(ReactionPolicyError):
        ReactionPolicy(latch_until_ack=False)


def test_a_non_default_strategy_is_allowed_with_frozen_latch() -> None:
    """The strategy may change; the latch flags may not."""
    policy = ReactionPolicy(strategy=ReactionStrategy.GRAVITY_COMP)
    assert policy.strategy is ReactionStrategy.GRAVITY_COMP
    assert policy.latch_until_ack is True
    assert policy.auto_resume is False
