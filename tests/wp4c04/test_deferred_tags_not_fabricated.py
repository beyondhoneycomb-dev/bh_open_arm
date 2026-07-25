"""Phase-2 deferral — the engine derives only the nine machine tags, never a human/FSM tag."""

from __future__ import annotations

from backend.eval.taxonomy import (
    CorrelationEngine,
    FailureTag,
    TagDerivation,
    deferred_tags,
    machine_tags,
    placeholder_taxonomy_thresholds,
    spec_for,
)
from backend.inference.runaway import DisconnectClass, FaultKind
from tests.wp4c04.support import joint_limit_clamp_record, nan_reject_record, signals


def test_exactly_nine_machine_tags() -> None:
    """The auto-derived set is exactly the nine machine tags."""
    assert len(machine_tags()) == 9


def test_the_four_deferred_tags_are_human_or_fsm() -> None:
    """POLICY_WRONG_ACTION / RESET_ERROR / AMBIGUOUS are HUMAN; TIMEOUT is FSM."""
    assert deferred_tags() == {
        FailureTag.POLICY_WRONG_ACTION,
        FailureTag.RESET_ERROR,
        FailureTag.AMBIGUOUS,
        FailureTag.TIMEOUT,
    }
    assert spec_for(FailureTag.TIMEOUT).derivation is TagDerivation.FSM
    for tag in (FailureTag.POLICY_WRONG_ACTION, FailureTag.RESET_ERROR, FailureTag.AMBIGUOUS):
        assert spec_for(tag).derivation is TagDerivation.HUMAN


def test_engine_output_never_contains_a_deferred_tag() -> None:
    """Across a battery of episodes the engine emits no human/FSM tag (the deferral)."""
    engine = CorrelationEngine(placeholder_taxonomy_thresholds())
    episodes = (
        signals(),
        signals(dual_records=(joint_limit_clamp_record(),)),
        signals(dual_records=(nan_reject_record(),), nan_inf_rejections=3),
        signals(fault_kind=FaultKind.RUNAWAY),
        signals(disconnect_class=DisconnectClass.TRANSPORT),
        signals(disconnect_class=DisconnectClass.EMPTY_ACTION),
        signals(queue_exhaustion_ratio=1.0),
        signals(safety_stop_count=1, collision_count=1, torque_limit_hits=1),
    )
    for episode in episodes:
        result = engine.correlate(episode)
        assert result <= machine_tags()
        assert result.isdisjoint(deferred_tags())
