"""CG-4C-04e — one episode may carry several tags; a failure rarely has one cause."""

from __future__ import annotations

from backend.eval.taxonomy import CorrelationEngine, FailureTag, placeholder_taxonomy_thresholds
from backend.inference.runaway import DisconnectClass, FaultKind
from tests.wp4c04.support import joint_limit_clamp_record, signals


def _engine() -> CorrelationEngine:
    return CorrelationEngine(placeholder_taxonomy_thresholds())


def test_compound_episode_yields_multiple_tags() -> None:
    """A clamp + safety stop + collision + torque limit produce four distinct tags."""
    tags = _engine().correlate(
        signals(
            dual_records=(joint_limit_clamp_record(),),
            safety_stop_count=1,
            collision_count=2,
            torque_limit_hits=1,
        )
    )
    assert {
        FailureTag.POLICY_OUT_OF_BOUNDS,
        FailureTag.SAFETY_STOP,
        FailureTag.COLLISION,
        FailureTag.TORQUE_LIMIT,
    } <= tags


def test_queue_starvation_over_threshold_co_occurs_with_runaway() -> None:
    """A queue-starvation runaway carries both POLICY_RUNAWAY and QUEUE_STARVATION."""
    thresholds = placeholder_taxonomy_thresholds()
    over = thresholds.queue_exhaustion_ratio_max + 0.1
    tags = CorrelationEngine(thresholds).correlate(
        signals(fault_kind=FaultKind.RUNAWAY, queue_exhaustion_ratio=over)
    )
    assert FailureTag.POLICY_RUNAWAY in tags
    assert FailureTag.QUEUE_STARVATION in tags


def test_healthy_episode_yields_no_tags() -> None:
    """An episode with clean signals produces the empty set."""
    assert _engine().correlate(signals()) == frozenset()


def test_queue_ratio_at_threshold_does_not_trip() -> None:
    """The threshold is exclusive — a ratio equal to the limit is not starvation."""
    thresholds = placeholder_taxonomy_thresholds()
    tags = CorrelationEngine(thresholds).correlate(
        signals(queue_exhaustion_ratio=thresholds.queue_exhaustion_ratio_max)
    )
    assert FailureTag.QUEUE_STARVATION not in tags


def test_remote_disconnect_stands_alone_when_isolated() -> None:
    """A pure transport loss produces exactly REMOTE_DISCONNECT."""
    tags = _engine().correlate(signals(disconnect_class=DisconnectClass.TRANSPORT))
    assert tags == frozenset({FailureTag.REMOTE_DISCONNECT})
