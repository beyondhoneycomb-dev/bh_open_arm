"""WP-2C-10 — the upstream feedback path: one in-process call quiesces the three sources.

When the collision reaction (WP-2C-05) confirms a trip, this package feeds it *upstream* —
releasing the teleoperator clutch, freezing the IK target at its last valid solution
(`05` FR-TEL-050), and discarding the policy action queue — so no new setpoint is produced
while the reaction latch holds. `12` FR-SAF-006: upstream and downstream are objects in the
same process, so the feedback is a single function call. v1's one-way-bridge constraint is
gone; an IPC- or network-routed implementation is the WP's `SUPERSEDED` branch.

Two invariants this package holds and does not restate elsewhere:

- **It never stops the command loop.** Stopping the stream drops the arm (RID-9 watchdog).
  These three surfaces suppress only *new* setpoints; the held setpoint keeps being sent by
  the downstream STOP_HOLD reaction (`backend.actuation` safety latch, reused by WP-2C-05),
  which this package neither imports nor duplicates.
- **The path is a call, not a message.** `locality` is the static check that no transport
  is imported anywhere in the package, the enforceable form of acceptance ②.
"""

from __future__ import annotations

from backend.feedback.feedback import (
    ACTION_CLUTCH_RELEASE,
    ACTION_IK_TARGET_FREEZE,
    ACTION_POLICY_QUEUE_DISCARD,
    FEEDBACK_ACTION_ORDER,
    CollisionTrip,
    FeedbackResult,
    UpstreamFeedback,
)
from backend.feedback.locality import (
    BANNED_TRANSPORT_MODULES,
    LocalityViolation,
    is_in_process,
    scan_imports,
)
from backend.feedback.sinks import IkTargetHold, PolicyActionQueue, TeleoperatorClutch

__all__ = [
    "ACTION_CLUTCH_RELEASE",
    "ACTION_IK_TARGET_FREEZE",
    "ACTION_POLICY_QUEUE_DISCARD",
    "BANNED_TRANSPORT_MODULES",
    "FEEDBACK_ACTION_ORDER",
    "CollisionTrip",
    "FeedbackResult",
    "IkTargetHold",
    "LocalityViolation",
    "PolicyActionQueue",
    "TeleoperatorClutch",
    "UpstreamFeedback",
    "is_in_process",
    "scan_imports",
]
