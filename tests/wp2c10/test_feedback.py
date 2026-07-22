"""WP-2C-10 acceptance ①: a collision trip releases the clutch, freezes the IK target,
and discards the action queue — each observed — in one synchronous, in-process call.

The doubles record each call rather than doing real work, so a passing test proves the
coordinator drove all three sources exactly once and returned an evidence record that
matches. A double never touches a socket or a command loop, so the feedback path being a
plain call is what makes these observations possible.
"""

from __future__ import annotations

from backend.feedback import (
    ACTION_CLUTCH_RELEASE,
    ACTION_IK_TARGET_FREEZE,
    ACTION_POLICY_QUEUE_DISCARD,
    FEEDBACK_ACTION_ORDER,
    CollisionTrip,
    UpstreamFeedback,
)


class RecordingClutch:
    """A teleoperator clutch double that counts releases."""

    def __init__(self) -> None:
        self.releases = 0

    def release(self) -> None:
        self.releases += 1


class RecordingIkTarget:
    """An IK target latch double that counts freezes."""

    def __init__(self) -> None:
        self.freezes = 0

    def freeze(self) -> None:
        self.freezes += 1


class RecordingQueue:
    """A policy action queue double holding a fixed backlog, cleared on discard."""

    def __init__(self, depth: int) -> None:
        self.depth = depth
        self.discards = 0

    def discard(self) -> int:
        self.discards += 1
        dropped = self.depth
        self.depth = 0
        return dropped


def _trip() -> CollisionTrip:
    """A representative confirmed trip.

    Returns:
        (CollisionTrip) A trip isolated to joint 3.
    """
    return CollisionTrip(joint_index=3, residual_nm=5.2, tripped_at=12.5)


def test_collision_trip_quiesces_each_source_once() -> None:
    clutch = RecordingClutch()
    ik_target = RecordingIkTarget()
    queue = RecordingQueue(depth=4)
    feedback = UpstreamFeedback(clutch, ik_target, queue)

    result = feedback.on_collision(_trip())

    assert clutch.releases == 1
    assert ik_target.freezes == 1
    assert queue.discards == 1
    assert result.discarded_actions == 4
    assert result.performed == FEEDBACK_ACTION_ORDER


def test_result_records_all_three_actions_in_order() -> None:
    feedback = UpstreamFeedback(RecordingClutch(), RecordingIkTarget(), RecordingQueue(depth=0))

    result = feedback.on_collision(_trip())

    assert result.performed == (
        ACTION_CLUTCH_RELEASE,
        ACTION_IK_TARGET_FREEZE,
        ACTION_POLICY_QUEUE_DISCARD,
    )


def test_empty_queue_reports_zero_discarded() -> None:
    queue = RecordingQueue(depth=0)
    feedback = UpstreamFeedback(RecordingClutch(), RecordingIkTarget(), queue)

    result = feedback.on_collision(_trip())

    assert result.discarded_actions == 0
    assert queue.discards == 1


def test_repeated_trip_is_safe_and_fires_each_time() -> None:
    clutch = RecordingClutch()
    ik_target = RecordingIkTarget()
    queue = RecordingQueue(depth=2)
    feedback = UpstreamFeedback(clutch, ik_target, queue)

    feedback.on_collision(_trip())
    second = feedback.on_collision(_trip())

    assert clutch.releases == 2
    assert ik_target.freezes == 2
    assert second.discarded_actions == 0


def test_feedback_holds_only_the_three_upstream_sources() -> None:
    clutch = RecordingClutch()
    ik_target = RecordingIkTarget()
    queue = RecordingQueue(depth=1)
    feedback = UpstreamFeedback(clutch, ik_target, queue)

    held = list(vars(feedback).values())

    assert held == [clutch, ik_target, queue]
