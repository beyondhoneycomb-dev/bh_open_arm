"""The three upstream sources a confirmed collision quiesces, as structural surfaces.

WP-2C-10 feeds a collision event *upstream* — to the teleoperator, the IK stage, and
the policy action queue — so that no new setpoint is generated while the reaction latch
holds. Each source is a `Protocol`: the real teleoperator, IK target holder, and policy
runtime satisfy these structurally, and a fault-injection double satisfies them too,
without this package importing any concrete upstream class. That is what keeps the
feedback path a direct in-process call rather than a second owner of any of those
subsystems (`12` FR-SAF-006).

None of these three stops the command loop. Stopping the stream would drop the arm
(RID-9 watchdog); the held setpoint keeps being sent by the downstream STOP_HOLD reaction
(`backend.actuation` safety latch, reused by WP-2C-05). These surfaces only stop *new*
setpoints from being produced.
"""

from __future__ import annotations

from typing import Protocol


class TeleoperatorClutch(Protocol):
    """The teleoperator's clutch — the gate that lets operator motion drive the follower.

    Releasing the clutch disengages the operator's input from command generation, so a
    hand still moving in the headset after a collision no longer produces new joint
    targets. Release is idempotent: releasing an already-released clutch is a no-op, so
    a chattering trip that fires the feedback twice is safe.
    """

    def release(self) -> None:
        """Disengage operator input from command generation."""
        ...


class IkTargetHold(Protocol):
    """The IK stage's target latch — holds the last valid joint target (`05` FR-TEL-050).

    Freezing latches the last valid IK solution as the standing target: the IK stage
    stops recomputing a target from fresh teleoperator poses, and it never jumps to a
    new solution. The latched target remains valid and keeps being sent by the downstream
    STOP_HOLD reaction — freezing suppresses *new* targets, it does not stop the stream.
    """

    def freeze(self) -> None:
        """Latch the last valid joint target and stop advancing it."""
        ...


class PolicyActionQueue(Protocol):
    """The policy runtime's queue of buffered action chunks awaiting execution.

    Discarding drops every queued chunk so no stale autonomous action executes after a
    collision — the queue may hold a chunk computed before the contact that would drive
    the arm back into it. Discard is idempotent and returns how many chunks it dropped,
    which is the feedback path's concrete evidence that the autonomous backlog was cut.
    """

    def discard(self) -> int:
        """Drop every queued action chunk; return the number discarded."""
        ...
