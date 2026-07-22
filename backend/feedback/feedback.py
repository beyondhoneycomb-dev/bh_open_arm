"""The upstream feedback coordinator — one in-process call that quiesces the three sources.

WP-2C-10. When the collision reaction (WP-2C-05) confirms a trip, `UpstreamFeedback`
drives the teleoperator clutch, the IK target latch, and the policy action queue in a
single synchronous call. `12` FR-SAF-006: because upstream and downstream are objects in
the same process, the feedback is one function call — v1's "the ROS bridge is one-way, so
a new path must be built" constraint is gone. Routing this over IPC or a network transport
is the `SUPERSEDED` branch of the WP, and `backend.feedback.locality` is the static check
that enforces it.

Call contract: `on_collision` is called inline in the process that owns the control loop,
on the trip-confirmation edge. Because the call is synchronous and inline, no command-loop
tick interleaves between the three actions, so their order is a matter of readability, not
a hazard window — the loop keeps sending the held setpoint throughout (STOP_HOLD is the
downstream reaction's job, not this path's).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.feedback.sinks import IkTargetHold, PolicyActionQueue, TeleoperatorClutch

# The feedback's action vocabulary, in execution order. Recorded in `FeedbackResult` and
# consumed as audit evidence that each of the three quiescing actions fired, once.
ACTION_CLUTCH_RELEASE = "clutch_release"
ACTION_IK_TARGET_FREEZE = "ik_target_freeze"
ACTION_POLICY_QUEUE_DISCARD = "policy_queue_discard"
FEEDBACK_ACTION_ORDER = (
    ACTION_CLUTCH_RELEASE,
    ACTION_IK_TARGET_FREEZE,
    ACTION_POLICY_QUEUE_DISCARD,
)


@dataclass(frozen=True)
class CollisionTrip:
    """A confirmed collision handed to the feedback path by the reaction stage.

    Carries the attribution the reaction confirmed, not a re-derivation: the feedback
    path never recomputes whether a collision happened, it only acts on the trip it is
    given (a single, in-process value pass — never a wire message).

    Attributes:
        joint_index: The joint the residual observer isolated the contact to.
        residual_nm: The residual magnitude that crossed threshold, newton-metres.
        tripped_at: The reaction's monotonic timestamp for the confirming edge, seconds.
    """

    joint_index: int
    residual_nm: float
    tripped_at: float


@dataclass(frozen=True)
class FeedbackResult:
    """The record of one feedback pass — evidence each source was quiesced.

    Attributes:
        trip: The collision that triggered this pass.
        discarded_actions: How many buffered policy action chunks were dropped.
        performed: The actions driven, in execution order (`FEEDBACK_ACTION_ORDER`).
    """

    trip: CollisionTrip
    discarded_actions: int
    performed: tuple[str, ...]


class UpstreamFeedback:
    """Drives clutch release, IK-target freeze, and action-queue discard as one call."""

    def __init__(
        self,
        clutch: TeleoperatorClutch,
        ik_target: IkTargetHold,
        action_queue: PolicyActionQueue,
    ) -> None:
        """Wire the feedback path onto the three upstream sources it quiesces.

        All three are required collaborators, not optional: the feedback drives every one
        unconditionally on a trip, so there is no silent branch where a source that should
        have been quiesced is skipped because a reference was `None`. A mode with no
        autonomous policy supplies a queue whose `discard` returns zero — a visible wiring
        choice, not a hidden gap.

        Args:
            clutch: The teleoperator clutch to release.
            ik_target: The IK target latch to freeze at the last valid solution.
            action_queue: The policy action queue to discard.
        """
        self._clutch = clutch
        self._ik_target = ik_target
        self._action_queue = action_queue

    def on_collision(self, trip: CollisionTrip) -> FeedbackResult:
        """Quiesce all three upstream sources for a confirmed collision, in one call.

        Order is cut-inputs (clutch), then latch the last valid target (IK), then drop the
        autonomous backlog (queue). The order is for readability only: the call is
        synchronous and inline, so no command-loop tick observes an intermediate state.

        Args:
            trip: The collision the reaction stage confirmed.

        Returns:
            (FeedbackResult) The record of the pass, including how many action chunks the
            queue discarded.
        """
        self._clutch.release()
        self._ik_target.freeze()
        discarded = self._action_queue.discard()
        return FeedbackResult(
            trip=trip,
            discarded_actions=discarded,
            performed=FEEDBACK_ACTION_ORDER,
        )
